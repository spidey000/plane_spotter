import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))  # Add project root to Python path
from config import config_manager
from log.logger_config import logger
config = config_manager.load_config()
from dotenv import load_dotenv

# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

env_path = Path(__file__).resolve().parent.parent / 'config' / '.env'  # Use the determined project_root
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"Loaded environment variables from: {env_path}")
else:
    logger.warning(f".env file not found at: {env_path}. Relying on system environment variables.")

load_dotenv()

# Use absolute import
from database import baserow_manager as bm
async def test_get_rows():
    # Test basic row retrieval
    print("Testing basic row retrieval...")
    rows = await bm.get_rows(f'{config['baserow']['tables']['registrations']}')  # Registrations table
    if rows:
        print(f"Successfully retrieved {len(rows)} rows")
        #print(rows)
    else:
        print("Failed to retrieve rows")

    # Test pagination
    print("\nTesting pagination...")
    print("\nTesting pagination with loop...")
    page = 1
    all_rows = []

    while True:
        rows = await bm.get_rows(f'{config['baserow']['tables']['registrations']}', page=page, size=100)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            break
        page += 1

    print(f"Total rows retrieved across all pages: {len(all_rows)}")
    # Save rows in a local dict with registration as key
    registrations_dict = {}
    for row in all_rows:
        if 'registration' in row and row['registration']:
            registrations_dict[row['registration']] = row
    print(f"Created dictionary with {len(registrations_dict)} registrations")

    # # Test filtering
    # print("\nTesting filtering...")
    # filtered_rows = await bm.get_rows(f'{config['baserow']['tables']['registrations']}', filters={"registration": "TEST123"})
    # if filtered_rows:
    #     print(f"Found {len(filtered_rows)} rows matching filter")
    # else:
    #     print("No rows found matching filter")

    # # Test ordering
    # print("\nTesting ordering...")
    # ordered_rows = await bm.get_rows(f'{config['baserow']['tables']['registrations']}', order_by="-registration")
    # if ordered_rows:
    #     print(f"First registration in descending order: {ordered_rows[0]['registration']}")
    # else:
    #     print("Failed to retrieve ordered rows")

    # # Test field selection
    # print("\nTesting field selection...")
    # selected_fields = await bm.get_rows(f'{config['baserow']['tables']['registrations']}', include="registration,first_seen")
    # if selected_fields:
    #     print(f"First row with selected fields: {selected_fields[0]}")
    # else:
    #     print("Failed to retrieve rows with selected fields")

async def get_all_rows_as_dict(table_id: int) -> dict:
    """Get all rows from a specified table and return as dictionary with registration as key"""
    page = 1
    all_rows = []
    
    while True:
        rows = await bm.get_rows(table_id, page=page, size=100)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            break
        page += 1
    
    registrations_dict = {}
    for row in all_rows:
        if 'registration' in row and row['registration']:
            registrations_dict[row['registration']] = row
    
    return registrations_dict

if __name__ == "__main__":
    asyncio.run(test_get_rows())