@"
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

Our web app is available in **English**, **中文 (Mandarin)**, and **日本語 (Japanese)**:

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
