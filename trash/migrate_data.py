import asyncio
import os
from loguru import logger
from config import config_manager
from database import baserow_manager as bm
from infrastructure.database.supabase_provider import SupabaseProvider

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

async def migrate_data():
    logger.info("Starting migration from Baserow to Supabase...")

    # 1. Load Config & Init Providers
    config = config_manager.load_config()
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL and SUPABASE_KEY must be set.")
        return

    supabase = SupabaseProvider(supabase_url, supabase_key)

    # 2. Migrate Interesting Models
    logger.info("Migrating Interesting Models...")
    try:
        table_id = config['baserow']['tables']['interesting_models']
        # Fetch all rows (pagination handled by get_all_rows_as_dict, but we want list)
        # We can use bm.get_rows loop or just get_all_rows_as_dict and iterate values
        models_dict = await bm.get_all_rows_as_dict(table_id, config, key='id') # Use ID as key to get all
        
        count = 0
        for row in models_dict.values():
            data = {
                "icao_code": row.get('model') or row.get('icao_code'), # Adjust based on actual Baserow field names
                "reason": row.get('reason'),
                "is_active": True
            }
            if data['icao_code']:
                try:
                    supabase.supabase.table("interesting_models").upsert(data, on_conflict="icao_code").execute()
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to insert model {data['icao_code']}: {e}")
        logger.success(f"Migrated {count} interesting models.")
    except Exception as e:
        logger.error(f"Error migrating interesting models: {e}")

    # 3. Migrate Interesting Registrations
    logger.info("Migrating Interesting Registrations...")
    try:
        table_id = config['baserow']['tables']['interesting_registrations']
        regs_dict = await bm.get_all_rows_as_dict(table_id, config, key='id')
        
        count = 0
        for row in regs_dict.values():
            data = {
                "registration": row.get('registration'),
                "reason": row.get('reason'),
                "is_active": True
            }
            if data['registration']:
                try:
                    supabase.supabase.table("interesting_registrations").upsert(data, on_conflict="registration").execute()
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to insert registration {data['registration']}: {e}")
        logger.success(f"Migrated {count} interesting registrations.")
    except Exception as e:
        logger.error(f"Error migrating interesting registrations: {e}")

    # 4. Migrate Registration History (Knowledge Base)
    logger.info("Migrating Registration History...")
    try:
        table_id = config['baserow']['tables']['registrations']
        # This might be large, so we should probably page through it
        page = 1
        total_count = 0
        while True:
            rows = await bm.get_rows(table_id, config, page=page, size=100)
            if not rows:
                break
            
            for row in rows:
                data = {
                    "registration": row.get('registration'),
                    "aircraft_type_icao": row.get('aircraft_type_icao') or row.get('model'),
                    "airline_icao": row.get('airline_icao') or row.get('airline'),
                    "image_url": row.get('image_url'),
                    # "first_seen_at": ... # Baserow might not have this, or it's 'created_on'
                    # "last_seen_at": ...
                }
                if data['registration']:
                    try:
                        # We use upsert_registration from provider which handles logic
                        await supabase.upsert_registration(data)
                        total_count += 1
                    except Exception as e:
                        logger.error(f"Failed to insert history {data['registration']}: {e}")
            
            logger.info(f"Processed page {page} ({total_count} records so far)")
            page += 1
            
        logger.success(f"Migrated {total_count} registration history records.")
    except Exception as e:
        logger.error(f"Error migrating registration history: {e}")

    logger.info("Migration completed.")

if __name__ == "__main__":
    asyncio.run(migrate_data())
