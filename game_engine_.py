import sys
import os
import time
import math
import json
import uvicorn
import threading
import webbrowser
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ============================================================
# Drone Command Center - Optimized Backend (smooth + bank/pitch)
# ============================================================

state_lock = threading.Lock()

# ==========================================
# 1. CONFIGURATION & LIFESPAN
# ==========================================

# NOTE: Keep your OpenAI key out of source control.
try:
    from openai import OpenAI
    client = OpenAI(api_key="[OPENAI_API_KEY]")  # uses OPENAI_API_KEY env var
except Exception:
    client = None

# --- LIFESPAN LOGIC (Fixes Deprecation & Pylance Warning) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Logic
    print("[SYSTEM] Server Starting...")
    
    def open_browser():
        time.sleep(1.5) # Wait for server to spin up
        webbrowser.open("http://127.0.0.1:8000/static/Drone_Command_Module.html")
    
    # Run browser launch in a separate thread so it doesn't block startup
    threading.Thread(target=open_browser, daemon=True).start()
    
    yield
    # Shutdown Logic (Optional)
    print("[SYSTEM] Server Shutting Down...")

START_COORDS = {
    "lat": 37.8120637,
    "lon": -122.3690327,
    "heading": 225.0,   # Facing South-West towards Ring 1
    "pitch": 0.0,
    "roll": 0.0,
    "alt": 120.0
}

drone_state = START_COORDS.copy()

RING_RADIUS_METERS = 25.0  # Increased slightly for easier gameplay

RINGS = [
    # 1. Treasure Island 
    {"id": 1, "lat": 37.8084672, "lon": -122.3744754, "alt": 110, "hit": False, "heading": 135, "roll": 0}, 

    # 2. Bay Bridge Approach 
    {"id": 2, "lat": 37.8013199, "lon": -122.3826108, "alt": 90,  "hit": False, "heading": 105, "roll": 0},  

    # 3. Market St 
    {"id": 3, "lat": 37.7906862, "lon": -122.3901824, "alt": 50,  "hit": False, "heading": 140, "roll": 0}, 

    # 4. Moscone Center 
    {"id": 4, "lat": 37.7854893, "lon": -122.3968166, "alt": 100, "hit": False, "heading": 180, "roll": 0}, 

    # 5. Union Square 
    {"id": 5, "lat": 37.7893323, "lon": -122.4012345, "alt": 100, "hit": False, "heading": 270, "roll": 0}, 

    # 6. Finish
    {"id": 6, "lat": 37.7938520, "lon": -122.3956155, "alt": 150, "hit": False, "heading": 315, "roll": 0} 
]

# SPEED SETTINGS (tune freely)
SPEED = 50.0          # meters/sec
CLIMB_SPEED = 12.0    # meters/sec (a bit faster so climb looks noticeable)

UPDATE_RATE = 0.01    # 100 Hz physics loop

# Visual attitude limits (degrees)
MAX_BANK_DEG = 45.0
MIN_BANK_DEG = 12.0
MAX_PITCH_DEG = 25.0  # more prominent climb/descend

# Initialize App with Lifespan
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

# Serves files from the script directory at /static/...
if getattr(sys, 'frozen', False):
    # If we are running as an EXE, use the temporary temp folder
    base_path = sys._MEIPASS
else:
    # If we are running as a script, use the current folder
    base_path = os.path.dirname(os.path.abspath(__file__))

app.mount("/static", StaticFiles(directory=base_path), name="static")


class Command(BaseModel):
    text: str

@app.get("/drone-data")
def get_telemetry():
    with state_lock:
        return {
            "drone": drone_state.copy(),
            "rings": RINGS
        }


@app.post("/reset")
def reset_game():
    global drone_state
    with state_lock:
        drone_state = START_COORDS.copy()
        
        # --- ADD THIS LOOP TO RESET RINGS ---
        for ring in RINGS:
            ring["hit"] = False
        # ------------------------------------
            
    print("[SYSTEM] RESET")
    return {"status": "Reset Complete"}


@app.post("/send-command")
def send_command(cmd: Command, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_flight_plan, cmd.text)
    return {"status": "Processing..."}


# ==========================================
# 2. LOW-LEVEL PHYSICS
# ==========================================

def _step_forward(distance_m: float):
    """Move forward by distance_m meters based on current heading."""
    with state_lock:
        heading = float(drone_state["heading"])
        lat = float(drone_state["lat"])

    rad = math.radians(heading)
    dy = math.cos(rad) * distance_m
    dx = math.sin(rad) * distance_m

    with state_lock:
        # Convert meters -> degrees (approx)
        drone_state["lat"] += dy / 111111.0
        drone_state["lon"] += dx / (111111.0 * max(0.000001, math.cos(math.radians(drone_state["lat"]))))
        # keep within ranges if you ever do extreme moves (optional)

def check_collisions():
    """Checks if drone is close enough to any un-hit ring."""
    with state_lock:
        d_lat = drone_state["lat"]
        d_lon = drone_state["lon"]
        d_alt = drone_state["alt"]
        
        for ring in RINGS:
            if ring["hit"]: continue  # Skip already collected rings

            # Approximate meters conversion
            lat_m = (d_lat - ring["lat"]) * 111111.0
            lon_m = (d_lon - ring["lon"]) * 111111.0 * math.cos(math.radians(d_lat))
            alt_m = d_alt - ring["alt"]

            # 3D Distance
            dist = math.sqrt(lat_m**2 + lon_m**2 + alt_m**2)

            if dist < RING_RADIUS_METERS:
                ring["hit"] = True
                print(f" [GAME] *** RING {ring['id']} COLLECTED! ***")

def move_drone(distance_meters: float):
    steps = max(1, int(distance_meters / (SPEED * UPDATE_RATE)))
    per_step = distance_meters / steps
    print(f"   [PHYSICS] Moving {distance_meters:.1f}m ({steps} steps)")
    for _ in range(steps):
        _step_forward(per_step)
        check_collisions()
        time.sleep(UPDATE_RATE)


def smooth_turn(target_heading: float, turn_direction: str):
    """
    Smoothly turn while moving forward AND banking (roll).
    This fixes the main issue: previously heading/roll barely changed during the loop,
    so you saw no left/right roll and the heading snapped at the end.
    """
    with state_lock:
        start_heading = float(drone_state["heading"])

    # signed shortest diff in [-180, 180)
    diff = (target_heading - start_heading + 180.0) % 360.0 - 180.0

    # enforce direction if requested
    if turn_direction == "cw" and diff < 0:
        diff += 360.0
    elif turn_direction == "ccw" and diff > 0:
        diff -= 360.0

    abs_diff = abs(diff)
    if abs_diff < 0.5:
        with state_lock:
            drone_state["heading"] = target_heading % 360.0
            drone_state["roll"] = 0.0
        return

    # Duration scales with turn size; faster than before but still smooth
    duration = max(1.2, abs_diff / 35.0)  # seconds
    steps = max(1, int(duration / UPDATE_RATE))

    dir_text = "Right" if diff > 0 else "Left"
    print(f"   [PHYSICS] Turning {dir_text} {abs_diff:.1f}° over {duration:.2f}s ({steps} steps)")

    # Bank amount scales with turn size
    calc_bank = min(MAX_BANK_DEG, max(MIN_BANK_DEG, abs_diff / 2.2))
    max_bank = calc_bank if diff > 0 else -calc_bank

    # Keep forward speed during the turn for a smooth arc
    step_distance = SPEED * UPDATE_RATE

    for i in range(steps):
        progress = i / steps  # 0..1
        # smooth in/out so bank ramps and returns
        bank = max_bank * math.sin(progress * math.pi)

        # interpolate heading gradually
        heading_now = (start_heading + diff * progress) % 360.0

        with state_lock:
            drone_state["heading"] = heading_now
            drone_state["roll"] = bank

        _step_forward(step_distance)
        check_collisions()
        time.sleep(UPDATE_RATE)

    with state_lock:
        drone_state["heading"] = target_heading % 360.0
        drone_state["roll"] = 0.0


def change_altitude(amount_meters: float):
    steps = max(1, int(abs(amount_meters) / (CLIMB_SPEED * UPDATE_RATE)))
    total_time = steps * UPDATE_RATE

    vert_per_step = (amount_meters / steps)  # meters per tick
    print(f"   [PHYSICS] Altitude change {amount_meters:.1f}m over {total_time:.2f}s ({steps} steps)")

    # Stronger pitch cue (visual)
    max_pitch = MAX_PITCH_DEG if amount_meters > 0 else -MAX_PITCH_DEG
    step_distance = SPEED * UPDATE_RATE

    for i in range(steps):
        progress = i / steps
        pitch = max_pitch * math.sin(progress * math.pi)

        with state_lock:
            drone_state["alt"] += vert_per_step
            drone_state["pitch"] = pitch

        # keep moving forward while climbing/descending
        _step_forward(step_distance)
        check_collisions()
        time.sleep(UPDATE_RATE)

    with state_lock:
        drone_state["pitch"] = 0.0


# ==========================================
# 3. COMMAND PARSING / PLAN EXECUTION
# ==========================================

def _fallback_parse(user_input: str):
    """
    If OpenAI is unavailable, do a very small parser for:
      - 'continue 5km'
      - 'move 200m'
      - 'climb 50'
      - 'descend 20'
      - 'turn right 30'
      - 'turn left 90'
    """
    txt = user_input.strip().lower()
    cmds = []

    # distance
    import re
    m = re.search(r"(continue|move|forward)\s+([\d.]+)\s*(km|m)?", txt)
    if m:
        val = float(m.group(2))
        unit = m.group(3) or "m"
        dist_m = val * 1000.0 if unit == "km" else val
        cmds.append({"action": "move", "distance": dist_m})

    # climb/descend
    m = re.search(r"(climb|ascend|up)\s+([\d.]+)", txt)
    if m:
        cmds.append({"action": "climb", "value": float(m.group(2))})
    m = re.search(r"(descend|down)\s+([\d.]+)", txt)
    if m:
        cmds.append({"action": "climb", "value": -float(m.group(2))})

    # turns (relative degrees)
    m = re.search(r"(turn\s+right|right)\s+([\d.]+)", txt)
    if m:
        deg = float(m.group(2))
        with state_lock:
            cur = float(drone_state["heading"])
        cmds.append({"action": "rotate", "value": (cur + deg) % 360.0, "type": "absolute", "direction": "cw"})
    m = re.search(r"(turn\s+left|left)\s+([\d.]+)", txt)
    if m:
        deg = float(m.group(2))
        with state_lock:
            cur = float(drone_state["heading"])
        cmds.append({"action": "rotate", "value": (cur - deg) % 360.0, "type": "absolute", "direction": "ccw"})

    return cmds


def process_flight_plan(user_input: str):
    print(f"\n[RECEIVED] {user_input}")

    with state_lock:
        current_heading = float(drone_state["heading"])

    # If OpenAI isn't configured, fallback.
    if client is None:
        print("[WARN] OpenAI client unavailable; using fallback parser.")
        commands = _fallback_parse(user_input)
    else:
        # Use env var OPENAI_API_KEY
        # --- UPDATED PROMPT LOGIC BELOW ---
        system_instruction = f"""
You are a drone flight computer.
CURRENT HEADING: {current_heading} degrees.
Input: Natural language commands.
Output: ONLY a raw JSON list of commands.

Schema:
- Rotate: {{"action":"rotate","value":0-360,"type":"absolute","direction":"cw"|"ccw"}}
- Move:   {{"action":"move","distance": meters}}
- Alt:    {{"action":"climb","value": +/- meters}}

CRITICAL RULES:
1) Turn Right X: output NEW absolute heading (current + X). SET "direction": "cw".
2) Turn Left  X: output NEW absolute heading (current - X). SET "direction": "ccw".
3) Always output absolute heading 0-360.
4) If the user specifies a turn direction (Left/Right), YOU MUST set the "direction" field to match.
5) INTERPRET "rX" as "Turn Right X" and "lX" as "Turn Left X".
"""

        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_input}
                ]
            )
            clean = (resp.choices[0].message.content or "").replace("```json", "").replace("```", "").strip()
            print(f"[AI PLAN] {clean}")
            commands = json.loads(clean)
        except Exception as e:
            print(f"[WARN] OpenAI parse failed; using fallback. ({e})")
            commands = _fallback_parse(user_input)

    for cmd in commands:
        try:
            action = cmd.get("action")
            if action == "rotate":
                target = float(cmd["value"]) % 360.0
                direction = cmd.get("direction", "cw")
                smooth_turn(target, direction)
            elif action == "move":
                move_drone(float(cmd["distance"]))
            elif action == "climb":
                change_altitude(float(cmd["value"]))
        except Exception as e:
            print(f"[WARN] Bad command {cmd}: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")