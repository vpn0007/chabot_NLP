# Snowflake Database Configuration
# Update this file with your actual Snowflake credentials

# Snowflake Configuration
SNOWFLAKE_CONFIG = {
    'user': 'VPN0007',
    'password': 'Password@12345',
    'account': 'ckcbvbc-ce87215',  # Working format (without region suffix)
    'warehouse': 'COMPUTE_WH',
    'database': 'CHATBOT_WAREHOUSE',
    'schema': 'PUBLIC',
    'role': 'ACCOUNTADMIN' ,  # Optional
    'oscp_fail_open':True
}

# Note: This project is now Snowflake-specific only
# The chatbot will automatically connect to Snowflake using the above configuration
