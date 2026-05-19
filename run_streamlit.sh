#!/bin/bash

# Streamlit App Runner for Stock Agent
# This script runs the Stock Agent Streamlit application

echo "🚀 Starting Stock Agent Streamlit Application..."
echo "📊 Loading portfolio data..."
echo "💬 Initializing chat interface..."
echo ""

# Run Streamlit app
streamlit run streamlit_app.py --server.port 8501 --server.headless true