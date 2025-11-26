import asyncio
import os
import csv
from glob import glob
from datetime import datetime
from loguru import logger
from infrastructure.database.supabase_provider import SupabaseProvider
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def migrate_csv_data():
    logger.info("Starting migration from CSV files to Supabase...")

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL and SUPABASE_KEY must be set.")
        return

    supabase = SupabaseProvider(supabase_url, supabase_key)

    # Helper for batch upsert
    def batch_upsert(table, data, batch_size=100, on_conflict=None):
        total = len(data)
        for i in range(0, total, batch_size):
            batch = data[i:i+batch_size]
            try:
                if on_conflict:
                    supabase.supabase.table(table).upsert(batch, on_conflict=on_conflict).execute()
                else:
                    supabase.supabase.table(table).upsert(batch).execute()
                logger.info(f"Upserted batch {i//batch_size + 1}/{(total-1)//batch_size + 1} to {table}")
            except Exception as e:
                logger.error(f"Failed to upsert batch to {table}: {e}")

    # Helper to determine airport from filename
    def get_airport_from_filename(filename):
        filename_lower = filename.lower()
        if "lebl" in filename_lower:
            return "LEBL"
        # Add other airports here if needed
        return "LEMD" # Default as per user instruction

    # 1. Migrate Models
    model_files = glob("database/*models*.csv") + glob("database/*Table*.csv")
    
    for file_path in model_files:
        logger.info(f"Processing model file: {file_path}")
        airport_icao = get_airport_from_filename(os.path.basename(file_path))
        logger.info(f"Detected airport: {airport_icao}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                aircraft_models_batch = []
                interesting_models_batch = []
                
                for row in reader:
                    icao_code = row.get('model')
                    name = row.get('name')
                    
                    if icao_code:
                        # Global table, no airport_icao needed
                        aircraft_models_batch.append({
                            "icao_code": icao_code,
                            "name": name or icao_code,
                            "description": "Imported from Baserow"
                        })
                        # Per-airport table
                        interesting_models_batch.append({
                            "airport_icao": airport_icao,
                            "icao_code": icao_code,
                            "reason": "Legacy Import",
                            "is_active": True
                        })
                
                if aircraft_models_batch:
                    logger.info(f"Batch upserting {len(aircraft_models_batch)} aircraft models...")
                    batch_upsert("aircraft_models", aircraft_models_batch, on_conflict="icao_code")
                
                if interesting_models_batch:
                    logger.info(f"Batch upserting {len(interesting_models_batch)} interesting models for {airport_icao}...")
                    # Conflict on composite key (airport_icao, icao_code)
                    # Supabase Python client might need explicit constraint name or just columns
                    # If on_conflict is string, it's column names. For composite, use comma separated?
                    # Actually, for composite PK/Unique, we usually just let upsert handle it if we provide all keys.
                    # But explicit is better. Let's try "airport_icao, icao_code"
                    batch_upsert("interesting_models", interesting_models_batch) # Let Supabase infer from unique constraint

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

    # 2. Migrate Registrations
    reg_files = glob("database/*registrations*.csv")
    
    for file_path in reg_files:
        logger.info(f"Processing registration file: {file_path}")
        airport_icao = get_airport_from_filename(os.path.basename(file_path))
        logger.info(f"Detected airport: {airport_icao}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                registrations_batch = []
                interesting_regs_batch = []
                
                for row in reader:
                    registration = row.get('registration')
                    first_seen = row.get('first_seen')
                    last_seen = row.get('last_seen')
                    reason = row.get('reason')
                    
                    if registration:
                        first_seen_dt = None
                        last_seen_dt = None
                        try:
                            if first_seen:
                                first_seen_dt = datetime.strptime(first_seen, "%Y-%m-%d %H:%M").isoformat()
                            if last_seen:
                                last_seen_dt = datetime.strptime(last_seen, "%Y-%m-%d %H:%M").isoformat()
                        except ValueError:
                            pass

                        reg_data = {
                            "airport_icao": airport_icao,
                            "registration": registration
                        }
                        if first_seen_dt: reg_data["first_seen_at"] = first_seen_dt
                        if last_seen_dt: reg_data["last_seen_at"] = last_seen_dt
                        
                        registrations_batch.append(reg_data)

                        if reason:
                            interesting_regs_batch.append({
                                "airport_icao": airport_icao,
                                "registration": registration,
                                "reason": reason,
                                "is_active": True
                            })
                
                if registrations_batch:
                    logger.info(f"Batch upserting {len(registrations_batch)} registrations for {airport_icao}...")
                    batch_upsert("registrations", registrations_batch)
                
                if interesting_regs_batch:
                    logger.info(f"Batch upserting {len(interesting_regs_batch)} interesting registrations for {airport_icao}...")
                    batch_upsert("interesting_registrations", interesting_regs_batch)

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

    logger.info("CSV Migration completed.")

if __name__ == "__main__":
    asyncio.run(migrate_csv_data())
