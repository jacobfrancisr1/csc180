# 🚚 Costco Night Merch Scheduler (Flask Version)

**Hybrid LLM + Deterministic Engine + Web UI**

This project is a fully automated scheduling system for **Costco Night Merchandising** operations. It generates a weekly driver/stocker schedule using:

- Employee skill rankings  
- Weekly availability matrix  
- Local LLM inference (llama3, phi3, etc.)  
- Deterministic fallback engine  
- A Google-Sheets-style HTML results table  

The system runs in a Flask web application with CSV uploads and a browser-based interface.

---

## ✨ Features

### 🔹 Hybrid Scheduling (LLM + Deterministic)
1. The LLM attempts the schedule first using templates and candidate lists.  
2. The system validates the LLM output:  
   - No duplicate employees  
   - Only assign available employees  
   - Exactly 15 roles per day  
3. If invalid → deterministic fallback produces a guaranteed valid schedule.

### 🔹 Deterministic Engine (Fallback)
If the LLM output is invalid, the deterministic engine fills roles in priority order:

#### Drivers  
- DOCK  
- EPJ  
- WALLS  
- FREEZER driver  
- DDD  
- FLOAT (best remaining employee)

#### Stockers  
- FREEZER × 5  
- WALLS × 3  
- BEER × 1  

Any unused workers become **EXTRAS** for that day.

### 🔹 Web UI
- Upload your Skills and Weekly Schedule CSV files  
- Click "Run" to generate the full weekly schedule  
- View the formatted results table  
- Download schedule.txt  

### 🔹 Google Sheets Style Output
The included HTML renderer creates a visually clean table with grouped sections:
- DRIVERS  
- STOCKERS  
- STOCKERS_EXTRAS  

---

## Installation

### 1. Install Python 3.10+
python3 --version

### 2. Install dependencies
pip install flask pandas requests

### 3. Install and run Ollama (or another local LLM backend)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3
ollama serve

### 4. Recommended Structure
scheduler/
│ app.py
│ README.md
│
├── templates/
│   ├── index.html
│   └── result.html

### 5. CSV File Formats
employee_skills.csv
name,dock,epj,walls,ddd,freezer_driver,freezer_stocker,walls_stocker,beer_stocker
Jacob,3,3,3,3,2,3,3,3

### 6. Schedule File Formats
employee_schedule.csv
name,Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday
Jacob,1,1,1,1,1,1,0





