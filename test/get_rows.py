import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import get_database_provider


async def inspect_provider_data() -> None:
    provider = get_database_provider()
    airport_icao = "LEMD"

    registrations = await provider.get_registrations_index(airport_icao)
    interesting_registrations = await provider.get_interesting_registrations_index(airport_icao)
    interesting_models = await provider.get_interesting_models_index(airport_icao)

    print(f"registrations: {len(registrations)}")
    print(f"interesting registrations: {len(interesting_registrations)}")
    print(f"interesting models: {len(interesting_models)}")


if __name__ == "__main__":
    asyncio.run(inspect_provider_data())
