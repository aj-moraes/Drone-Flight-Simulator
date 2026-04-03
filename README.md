## 🎯 Mission Objective
The goal of this simulation is to pilot an autonomous UAS through a high-fidelity 3D Digital Twin of San Francisco to collect six localized "Red Rings." This serves as a demonstration of **Next-Generation Command & Control (C2)** interfaces where human-machine teaming is prioritized through Natural Language Processing.
<img width="2541" height="1260" alt="image" src="https://github.com/user-attachments/assets/10e242f4-a165-4cc7-9a56-5cf59775074b" />

## 🛠️ The Technical "Deep Dive"
* **Visual Layer (Frontend):** Utilizing the **ArcGIS Maps SDK for JavaScript** to render sub-meter accurate 3D building layers and terrain.
* **Logic Layer (Backend):** A high-performance **Python (FastAPI)** microservice that manages real-time physics, drone telemetry, and proximity detection.
* **AI Integration:** The **OpenAI API** acts as a translation layer, converting unstructured human speech (e.g., *"Dip 50m and bank left"*) into structured JSON flight vectors in real-time.



## 💡 Operational Value
This project demonstrates how to modernize federal and defense workflows by:
* **Lowering the Barrier to Entry:** Operators can focus on the mission using plain English rather than mastering complex flight controller software.
* **Digital Twin Readiness:** Proves that existing geospatial data and 3D environments are mission-ready for simulation and wargaming.
* **Risk-Free Wargaming:** The underlying engine provides a sandbox for simulating autonomous vehicle paths, logistics disruptions, or Red vs. Blue scenarios.

## 🎮 How to Fly (AI Commands)
The drone understands natural language instructions. You can combine or vary your commands:
* **Move:** *"Move forward 500m"* or *"Advance 1km"*
* **Turn:** *"Turn left 45 degrees"* or *"Bank right 90"*
* **Altitude:** *"Climb 50m"*, *"Descend 20m"*, or *"Dip 10m"*
