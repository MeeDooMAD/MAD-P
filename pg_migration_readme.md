# PostgreSQL Migration Guide

This document outlines the steps to migrate the vehicle dropoff management system from SQLite to PostgreSQL.

## Prerequisites

1. Ensure PostgreSQL is installed and running
2. Make sure the DATABASE_URL environment variable is set with a valid PostgreSQL connection string

## Migration Steps

1. **Create PostgreSQL Database Tables**

   Run the following command to create the necessary tables in PostgreSQL:

   ```bash
   python -c "from app_pg import app; from models_pg import db; app.app_context().push(); db.create_all()"
   ```

2. **Migrate Data from SQLite to PostgreSQL**

   Run the migration script to transfer all existing data from SQLite to PostgreSQL:

   ```bash
   python migrate_to_postgres.py
   ```

   This script will:
   - Read all data from the SQLite database
   - Convert date strings to proper datetime objects
   - Insert all records into PostgreSQL
   - Maintain relationships between dropoffs and maintenance alerts
   - Generate a summary of the migration process

3. **Verify Migration**

   After migration, you can verify the data has been transferred correctly by:
   
   ```bash
   python -c "from app_pg import app; from models_pg import db, Dropoff, MaintenanceAlert; app.app_context().push(); print(f'Dropoffs: {Dropoff.query.count()}, Alerts: {MaintenanceAlert.query.count()}')"
   ```

4. **Start PostgreSQL Version**

   Once migration is complete, you can run the PostgreSQL version of the application:

   ```bash
   python main_pg.py
   ```

   Or use Gunicorn:

   ```bash
   gunicorn --bind 0.0.0.0:5000 --reload app_pg:app
   ```

## Rollback Procedure

If you need to revert to SQLite, you can:

1. Stop the PostgreSQL version
2. Restart the original SQLite version:

   ```bash
   python app.py
   ```

   Or:

   ```bash
   gunicorn --bind 0.0.0.0:5000 --reload main:app
   ```

## Benefits of PostgreSQL

1. Better concurrency and performance for multi-user environments
2. Advanced data types (JSON, arrays, etc.)
3. Robust transaction support
4. Better data integrity with constraints and foreign keys
5. Superior indexing capabilities for faster querying
6. Better security features