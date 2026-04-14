# SCB Financial Markets Intelligence Dashboard

A dashboard that scans financial news and recommends
Standard Chartered FX, rates and commodities products
to the sales team — with client targeting and pitch angles.

---

## Setup (step by step — beginner friendly)

### Step 1 — Install Python
If you don't have Python installed:
- Go to https://python.org/downloads
- Download Python 3.11 or newer
- During install, CHECK the box that says "Add Python to PATH"

### Step 2 — Download this project
Put the entire `scb-dashboard` folder somewhere on your computer,
for example: `C:\Users\YourName\Desktop\scb-dashboard`

### Step 3 — Open a terminal in the project folder
- On Windows: open the folder, click the address bar, type `cmd`, press Enter
- On Mac: right-click the folder → "New Terminal at Folder"

### Step 4 — Install dependencies
Type this in the terminal and press Enter:
```
pip install -r requirements.txt
```
Wait for everything to install (takes 1-2 minutes).

### Step 5 — Get your free API keys

**Groq API key (powers AI recommendations):**
1. Go to https://console.groq.com
2. Sign up with your email (free)
3. Click "API Keys" → "Create API Key"
4. Copy the key

**NewsAPI key (more news sources):**
1. Go to https://newsapi.org
2. Click "Get API Key" → sign up (free)
3. Copy the key from your dashboard

### Step 6 — Set up your API keys
1. Find the file called `.env.example` in the project folder
2. Copy it and rename the copy to exactly `.env` (no .example)
3. Open `.env` in Notepad
4. Replace `your_groq_key_here` with your actual Groq key
5. Replace `your_newsapi_key_here` with your actual NewsAPI key
6. Save the file

### Step 7 — Run the dashboard
In your terminal, type:
```
streamlit run app.py
```
The dashboard will open automatically in your browser at http://localhost:8501

---

## Project file structure

```
scb-dashboard/
├── app.py              ← Main dashboard (start here to understand the UI)
├── news_fetcher.py     ← Pulls headlines from RSS + NewsAPI
├── trend_detector.py   ← Keyword scanning — maps news to trends
├── ai_recommender.py   ← Calls Groq AI for recommendations
├── config.py           ← All settings (feeds, products, keys)
├── requirements.txt    ← Python packages needed
├── .env.example        ← Template for your API keys
└── .env                ← Your actual keys (you create this, never share it)
```

## How it works (plain English)

1. Every 15 minutes, `news_fetcher.py` pulls headlines from RSS feeds and NewsAPI
2. `trend_detector.py` scans those headlines for financial keywords
3. If strong signals are found, `ai_recommender.py` sends them to Groq (Llama 3)
4. The AI returns structured recommendations: product, client, why now, pitch
5. `app.py` displays everything in a clean dashboard

## Deploying to the web (after your prototype is working)

The easiest path (free, no server knowledge needed):
1. Push your code to a private GitHub repository
2. Go to https://render.com and sign up
3. Click "New Web Service" → connect your GitHub repo
4. Set environment variables (your API keys) in Render's dashboard
5. Deploy — Render gives you a public URL in ~5 minutes

For AWS deployment, ask your manager about EC2 t2.micro (free tier).

## Customising the recommendation logic

The most important file for your project is `trend_detector.py`.
The `TREND_TAXONOMY` dictionary is where you map keywords to products.
After your manager meetings, update this dictionary to reflect:
- Which client segments SC is targeting right now
- Which products the FM division wants to push
- Which EM markets are priorities
