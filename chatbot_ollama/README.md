# Snowflake SQL Query Chatbot

A web-based chatbot that converts natural language queries to SQL and executes them against a Snowflake database.

## Features

- **Natural Language to SQL**: Convert English statements to SQL queries using Ollama LLM
- **Snowflake Integration**: Direct connection to Snowflake cloud database
- **Web UI**: Modern, responsive interface with table results display
- **Smart JOIN Logic**: Intelligent handling of bridge tables and logical relationships
- **Sticky Table Headers**: Fixed column headers during horizontal scrolling
- **Export Functionality**: Download results as CSV
- **Conversation History**: Maintains context across multiple queries

## Prerequisites

1. **Python 3.8+**
2. **Ollama** with `llama3.1` model installed and running
3. **Snowflake Account** with proper credentials

## Installation

1. **Clone or download the project**
2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Snowflake connection in `config.py`:**
   ```python
   SNOWFLAKE_CONFIG = {
       'user': 'YOUR_USERNAME',
       'password': 'YOUR_PASSWORD',
       'account': 'YOUR_ACCOUNT_ID',
       'warehouse': 'YOUR_WAREHOUSE',
       'database': 'YOUR_DATABASE',
       'schema': 'YOUR_SCHEMA',
       'role': 'YOUR_ROLE'
   }
   ```

## Usage

1. **Start Ollama with llama3.1:**
   ```bash
   ollama run llama3.1
   ```

2. **Run the Flask application:**
   ```bash
   python app.py
   ```

3. **Open your browser** to `http://localhost:5004`

4. **Initialize the database connection** by clicking "Initialize Database Connection"

5. **Enter your query** in natural language (e.g., "show me all patients with diabetes")

## Example Queries

- "Show me first 10 rows from DIMPATIENT table"
- "Find patients with chronic diseases and their severity"
- "Count patients by nationality and gender"
- "Show me encounters with corresponding doctor information"
- "Find patients with both allergies and chronic conditions"

## Project Structure

```
chatbot_ollama/
├── app.py              # Main Flask application
├── config.py           # Snowflake configuration
├── requirements.txt    # Python dependencies
├── templates/
│   └── sql.html       # Web UI template
└── README.md          # This file
```

## Troubleshooting

- **Port conflicts**: If port 5004 is in use, the app will automatically find an available port
- **Ollama not running**: Ensure `ollama run llama3.1` is running before starting the app
- **Snowflake connection issues**: Verify credentials in `config.py` and network connectivity
- **Table display issues**: Check browser console for JavaScript errors

## Features

- **Responsive Design**: Works on desktop and mobile devices
- **Smart Scrolling**: Horizontal and vertical scrolling with sticky headers
- **Data Export**: Download results as CSV files
- **Full Table View**: Open complete results in new tab
- **Error Handling**: Clear error messages and debugging information
