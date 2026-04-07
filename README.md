# OPC UA SQL Bridge

Broadcasts SQL Server tag values over OPC UA.
Comes with a web UI for managing which tags to expose.

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Install the ODBC driver for SQL Server
#    https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

# 3. Edit config.py
#    - Set DEMO_MODE = False and fill in SQL_SERVER_CONN for a real DB
#    - Leave DEMO_MODE = True to test with random values (no SQL Server needed)

# 4. Run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

The OPC UA server listens on **opc.tcp://localhost:4840/opcua/bridge**.

---

## REST API

| Method | Path | Description |
|--------|------|-------------|
| GET    | /api/status         | Server status + tag counts |
| GET    | /api/tags           | All tags with live values  |
| POST   | /api/tags           | Create a tag               |
| PUT    | /api/tags/{id}      | Update a tag               |
| PATCH  | /api/tags/{id}/enabled?enabled=true | Toggle enabled |
| DELETE | /api/tags/{id}      | Delete a tag + OPC node    |
| GET    | /api/cache          | Raw in-memory cache dump   |

---

## Tag data types

| Type         | OPC UA type   | SQL return value                               |
|--------------|---------------|------------------------------------------------|
| Float        | Double        | Single numeric column                          |
| Int32        | Int32         | Single integer column                          |
| Boolean      | Boolean       | 0/1 or true/false                              |
| String       | String        | Single text column                             |
| FloatArray   | Double[]      | Multiple values (columns or rows)              |
| Int32Array   | Int32[]       | Multiple integer values (columns or rows)      |
| BooleanArray | Boolean[]     | Multiple boolean-like values (columns or rows) |
| StringArray  | String[]      | Multiple text values (columns or rows)         |

### Array example queries
```sql
SELECT axis_x, axis_y, axis_z FROM vibration_sensors WHERE sensor_id = 42
```

```sql
SELECT sample_value FROM vibration_samples WHERE sensor_id = 42 ORDER BY ts DESC
```

### Efficiency tips
- Use `WITH (NOLOCK)` or set `DEMO_MODE = False` with `READ UNCOMMITTED`
  (already set in the engine) to avoid locking production tables.
- Group tags that can share a common interval — the engine runs
  **one query per tag** per cycle, but all tags in a group run
  concurrently inside a single DB connection.
- Minimum poll interval is 500 ms (enforced in config.py).
