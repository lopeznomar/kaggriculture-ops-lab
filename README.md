# 🌾 Kaggriculture Ops Lab

[![Kaggle](https://img.shields.io/badge/Kaggle-Kaggriculture-blue)](https://www.kaggle.com/competitions/kaggriculture)
[![Python](https://img.shields.io/badge/Python-3.8%2B-green)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/badge/Stars-⭐-yellow)](https://github.com/lopeznomar/kaggriculture-ops-lab/stargazers)

> **Open-source analytics and decision-support tools for Kaggriculture AI agents.**

Upload replay JSON files to generate P&L reports, production insights, cost diagnostics, and actionable optimization recommendations.

---

## 🌐 Try it Online!

**Get instant insights without installing anything!**

Our web app is available in **8 languages**:

| Language | Flag |
|----------|------|
| English | 🇬🇧🇺🇸 |
| 中文 (Mandarin) | 🇨🇳 |
| 日本語 (Japanese) | 🇯🇵 |
| हिन्दी (Hindi) | 🇮🇳 |
| Español (Spanish) | 🇪🇸 |
| Русский (Russian) | 🇷🇺 |
| Português (Portuguese) | 🇵🇹 |
| 한국어 (Korean) | 🇰🇷 |

👉 **[kaggriculture-ops-lab.lovable.app](https://kaggriculture-ops-lab.lovable.app)**

**Web App Features:**
- 📊 **Quick Dashboard**: Key metrics in seconds
- 📈 **P&L Statement**: Automatic profit & loss analysis
- 🎯 **Cost Spike Detection**: Identify abnormal expenses
- 🗺️ **Operational Reports**: Visualize your agent's performance

---

## 📊 What is this?

**Kaggriculture Ops Lab** is a Python toolkit designed to help competitors in the [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture) simulation competition. It parses replay files and generates detailed **Profit & Loss (P&L) reports** with:

- 📈 **Interactive visualizations** of wealth evolution and market prices
- 🗺️ **Cost Center Analysis** - Track profitability per quadrant/land parcel
- 🎯 **Market timing recommendations** based on price elasticity
- 🧪 **Strategy optimization** comparing ROI across crops and animals
- 🔍 **Diagnostic tools** for spike detection, stall analysis, and monocrop diagnosis

---

## 💼 Business Model (How It Works)

**Kaggriculture Ops Lab is 100% free and open source.** There is no paywall, no subscription, and no hidden fees.

However, this project is maintained by a single developer. If the toolkit helps you improve your agent, you can support future development through:

| Method | Link / ID | What it supports |
|--------|-----------|------------------|
| **PayPal** | [paypal.me/lopeznomar](https://paypal.me/lopeznomar) | Server costs, development time |
| **Binance Pay** | 36735348 | Infrastructure and maintenance |
| **GitHub Sponsors** | Coming soon | Long-term sustainability |

**Why is this important?**

This is not a commercial product — it's a community-driven project. Your support helps keep it alive and evolving.

---

## ✨ Key Features

### 📈 P&L Reports
- Cash vs Total Wealth (Cash + Inventory Value) evolution
- Daily revenue and expense tracking
- Cumulative profit/loss over the season
- Final wealth breakdown by asset type
- **Profit by crop/animal type** with visual charts

### 🗺️ Cost Center Analysis
Analyze each land quadrant as an independent cost center:
- Track **revenue, costs, and profit** per quadrant (NW, NE, SW, SE)
- Identify your **most profitable land parcels**
- Measure **RoI per tile** and **profit per tile per day**
- Compare performance between **crops vs animals** per quadrant
- Detect **underperforming quadrants** that need strategy changes

### 📊 Market Intelligence
- Price evolution tracking for all products (WHEAT, CARROT, TOMATO, STRAWBERRY, MELON, EGG, MILK, WOOL, FERTILIZER)
- **Sell/Buy timing recommendations** based on percentile analysis
- Price elasticity metrics
- Order analysis (BUY_SEED, BUY_ANIMAL, SELL)

### 🔍 Diagnostic Tools
- **Spike Investigation**: Find exactly why your money jumped
- **Stall Analysis**: Track every unit (farmer + hands) turn-by-turn
- **Monocrop Diagnosis**: Check if your agent got stuck on one crop
- **Labor Analysis**: Real hiring costs, tiles-per-hand ratio, weed correlation
- **Land & Crop Tracking**: See when land was bought and what's planted

### ⚔️ Player Comparison
- **Side-by-side** wealth tracking vs rivals
- **Crop and animal** distribution comparison
- **Early game tempo** analysis (turn-by-turn for first N days)

### 🧪 Strategy Optimizer
- **ROI comparison** across all crops (with/without fertilizer)
- Break-even analysis
- Daily ROI calculation for time-sensitive decisions

### 🎯 Performance Metrics
- Wealth Growth Rate (logarithmic)
- Inventory Turnover rate
- Labor Efficiency (profit per hired hand)
- Land Utilization percentage
- Production Efficiency (harvest per tile)

---

## 🛠️ Local Scripts vs Web App

| Feature | Web App | Local Scripts |
|---------|---------|---------------|
| P&L Statement | ✅ | ✅ (More detailed) |
| Profit by Type | ✅ | ✅ |
| Cost Spike Detection | ✅ | ✅ |
| **Cost Center Analysis** | ❌ | ✅ |
| **Labor Efficiency** | ⏳ In Development | ✅ |
| **Player Comparison** | ❌ | ✅ |
| **Spike Investigation** | ❌ | ✅ |
| **Stall Investigation** | ❌ | ✅ |
| **Monocrop Diagnosis** | ❌ | ✅ |
| **CSV Export** | ❌ | ✅ |
| **Offline Usage** | ❌ | ✅ |

**Why use the local scripts?**
- 🔍 **Deep Diagnostics**: Investigate specific issues (spikes, stalls)
- 📊 **Cost Center Analysis**: Know exactly which land quadrant is making you money
- 👷 **Labor ROI**: Measure the real cost and value of hired hands
- 📁 **Full Data Export**: Generate CSV files for your own analysis
- 💻 **Offline & Customizable**: Run it anywhere, modify it to fit your needs

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/lopeznomar/kaggriculture-ops-lab.git
cd kaggriculture-ops-lab

# Install dependencies
pip install -r requirements.txt
Using the Unified Script (Recommended)
bash
# List all available commands
python main.py --list

# Full analysis (all reports)
python main.py all replay.json --output outputs/

# P&L Statement only
python main.py pnl replay.json "RamónLópez"

# Cost Center Analysis
python main.py cost-center replay.json "RamónLópez"

# Labor Analysis
python main.py labor replay.json "RamónLópez"

# Compare both players
python main.py compare replay.json

# Early game tempo (first 3 days)
python main.py tempo replay.json "RamónLópez" 3

# Investigate a money spike
python main.py spike replay.json "RamónLópez"

# Investigate stalling
python main.py stall replay.json "RamónLópez"

# Diagnose monocrop
python main.py monocrop replay.json
Using Individual Scripts
bash
# Full P&L Statement
python profit_loss_statement.py replay.json

# Profit by type (crops vs animals)
python profit_by_type.py replay.json "RamónLópez"

# Cost Center Analysis per quadrant
python cost_center_by_quadrant.py replay.json "RamónLópez"

# Labor analysis (hiring costs, land-to-labor ratio)
python labor_analysis.py replay.json "RamónLópez"

# Compare both players side-by-side
python compare_both_players.py replay.json

# Early game tempo (turn by turn)
python compare_early_game_tempo.py replay.json 3

# Investigate a money spike
python investigate_spike.py replay.json "RamónLópez" 20 25

# Check if your agent is stalling
python investigate_stall.py replay.json "RamónLópez" 1 3

# Diagnose monocrop
python diagnose_monocrop.py replay.json 20 25
📊 Generated Outputs
Script	Output File	Description
profit_loss_statement.py	estado_resultados.png	P&L chart with expense breakdown
profit_by_type.py	profit_by_type.png	Profit by crop/animal type
cost_center_by_quadrant.py	cost_center_by_quadrant.png	Cost center comparison chart
labor_analysis.py	labor_analysis.png	Labor metrics (hands vs land, weeds)
💡 Pro Tips
1. Identify your player index automatically
Most scripts detect "RamónLópez" automatically (with or without accents). If you're using a different team name:

bash
python profit_by_type.py replay.json "YourTeamName"
2. Cost Center Analysis
The cost center analysis treats each quadrant as a business unit:

Direct costs: seeds, animals (attributed by position)

Indirect costs: labor (prorated by activity)

Revenue: book value (max yield × price at harvest time)

3. Labor Analysis
The real hiring cost is calculated as a residual (not using the Fibonacci formula) because the game silently rejects excessive HIRE orders. This method ensures the P&L always matches the actual money.

4. Spanish vs English Scripts
The project includes scripts in both Spanish (analizar_*.py) and English. The unified main.py handles both seamlessly.

5. Auto-detection of Player Index
All scripts automatically detect your player index using the team name from the replay file. This solves the issue where your player index (0 or 1) changes between games.

📋 Command Reference
Command	Description	Example
pnl	Full P&L Statement	python main.py pnl replay.json
profit	Profit by crop/animal	python main.py profit replay.json "RamonLopez"
cost-center	Cost Center Analysis	python main.py cost-center replay.json "RamonLopez"
labor	Labor Analysis	python main.py labor replay.json "RamonLopez"
compare	Compare both players	python main.py compare replay.json
tempo	Early game tempo	python main.py tempo replay.json "RamonLopez" 3
spike	Investigate money spike	python main.py spike replay.json "RamonLopez"
stall	Investigate stall	python main.py stall replay.json "RamonLopez"
monocrop	Diagnose monocrop	python main.py monocrop replay.json
all	Run all analyses	python main.py all replay.json --output outputs/
🤝 Contributing
Contributions are welcome! Here's how you can help:

Areas where help is needed:
Add support for multi-agent comparison

Implement ML-based strategy recommendations

Create a Streamlit dashboard

Add more visualizations

Translate scripts to other languages

How to contribute:
Fork the repository

Create a feature branch (git checkout -b feature/amazing-feature)

Commit your changes (git commit -m 'Add some amazing feature')

Push (git push origin feature/amazing-feature)

Open a Pull Request

📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

🙏 Acknowledgments
Kaggle for hosting the competition

The Kaggriculture competition organizers

All contributors and users of this toolkit

☕ Support the Project
Kaggriculture Ops Lab is 100% free and open source.

If this toolkit helped you improve your agent and you'd like to support future development:

Platform	Link / ID
PayPal	paypal.me/lopeznomar
Binance Pay	36735348
All contributions are voluntary and greatly appreciated! 🙏

📬 Contact
Issues: GitHub Issues

Discussions: GitHub Discussions

⚖️ Legal & Disclaimer
Kaggriculture Ops Lab is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Kaggle or any of its partners.

All tools, scripts, and analyses are provided "as is" for educational and competitive purposes. Use them at your own risk.

⭐ Star this repository if you find it useful!

Made with ❤️ for the Kaggriculture community in Venezuela and around the world.

