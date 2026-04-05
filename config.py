# ──────────────────────────────────────────────
#  Set DEMO_MODE = True to run without a real
#  SQL Server (uses random values for testing).
# ──────────────────────────────────────────────
DEMO_MODE = True

# ── SQL Server connection string ──────────────
SQL_SERVER_CONN = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\SQLEXPRESS;"
    "DATABASE=Production;"
    "UID=sa;"
    "PWD=YourPassword;"
    "TrustServerCertificate=yes;"
)

# ── OPC UA server settings ───────────────────
OPC_ENDPOINT  = "opc.tcp://0.0.0.0:4840/opcua/bridge"
OPC_NAMESPACE = "http://opcua.sqlbridge"

# ── Internal settings ────────────────────────
REGISTRY_DB = "registry.db"
MIN_POLL_MS  = 500          # floor for any poll interval
