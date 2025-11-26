# this is a script to manage the baserow database
# it will be used to store the flight airlines and aircraft models

# https://github.com/bram2w/baserow
# https://baserow.io/docs/index

import aiohttp
from loguru import logger
import datetime
# Removed dotenv import as we will rely on environment variables passed to the container
# from dotenv import load_dotenv
import os
import json
from config import config_manager # Keep import for type hinting or if other functions need it
from log.logger_config import logger
import asyncio

# Import cache manager
from database.cache_manager import cached_db_call, get_cached_rows_as_dict, get_cached_single_row


# import the credentials for the baserow

# all registrations table '441094'
# all models table '441095'
# to check interesting models '441097'
# to check interesting registrations '441099'


# Load the .env file

# Load the config file (removed global load)

def get_baserow_headers():
    """
    Helper function to generate Baserow headers with the token.
    :return: Dictionary containing the headers
    """
    BASEROW_TOKEN = os.getenv('BASEROW_TOKEN')
    return {
        "Authorization": f"Token {BASEROW_TOKEN}",
        "Content-Type": "application/json"
    }

async def query_table(table_id, config, filters=None, user_field_names=True):
    """
    Generic function to query any Baserow table
    :param table_id: ID of the table to query
    :param config: The configuration dictionary
    :param filters: Dictionary of filters to apply
    :param user_field_names: Whether to use human-readable field names
    :return: Response data or None if not found
    """
    if config is None:
        logger.error("Configuration (config) must be provided to query_table.")
        raise ValueError("Configuration is missing.")

    url = f"{config['baserow']['api_url']}{table_id}/"
    params = {"user_field_names": "true" if user_field_names else "false"}
    
    if filters:

        for field, value in filters.items():
            if isinstance(value, dict):
                # Extract value from filter dict if provided in advanced format
                value = value.get('value', '')
            params[f"filter__{field}__equal"] = str(value)
    
    headers = get_baserow_headers()

    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if len(data['results'])>0:
                            logger.debug(f"Successfully queried table {table_id} for filters {filters}")
                            return data['results'][0]
                        else:
                            logger.warning(f"No results found for table {table_id} for filters {filters}")
                            return None
                    else:
                        logger.warning(f"Error response {response.status} for table {table_id} for filters {filters}")
                        # Don't retry on 4xx errors (except maybe 429, but let's keep it simple)
                        if response.status < 500 and response.status != 429:
                            return None
            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/3 failed for table {table_id}: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        return None

async def query_cached_table(table_id, config, filters=None, user_field_names=True, ttl_seconds: int = 300):
    """
    Generic function to query any Baserow table with caching support
    :param table_id: ID of the table to query
    :param config: The configuration dictionary
    :param filters: Dictionary of filters to apply
    :param user_field_names: Whether to use human-readable field names
    :param ttl_seconds: Cache TTL in seconds
    :return: Response data or None if not found
    """
    return await get_cached_single_row(table_id, config, filters, ttl_seconds)
        
async def query_registrations_table(flight, config):
    logger.debug(f"Querying registrations table for flight {flight['registration']}")
    return await query_table(
        table_id=config['baserow']['tables']['registrations'],  # Registrations table ID
        config=config,
        filters={"registration": flight['registration']}
    )

async def query_interesting_registrations_table(flight, config):
    logger.debug(f"Querying interesting registrations table for flight {flight['registration']}")
    return await query_table(
        table_id=config['baserow']['tables']['interesting_registrations'],  # Interesting registrations table ID
        config=config,
        filters={"registration": flight['registration']}
    )

async def query_interesting_models_table(flight, config):
    model = flight['aircraft_name']
    if model:
        logger.debug(f"Querying interesting models table for model {model}")
        model_query = await query_table(
            table_id=config['baserow']['tables']['interesting_models'],  # Interesting models table ID
            config=config,
            filters={"name": model}
        )
        return model_query
    else:
        model = flight['aircraft_icao']
        logger.debug(f"Querying interesting models table for model {model}")
        model_query = await query_table(
            table_id=config['baserow']['tables']['interesting_models'],  # Interesting models table ID
            config=config,
            filters={"model": model}
        )
        return model_query


async def create_record(table_id, data, config):
    """
    Generic function to create a record in any Baserow table
    :param table_id: ID of the table to create record in
    :param data: Dictionary of data to create
    :param config: The configuration dictionary
    :return: Created record data or None if failed
    """
    if config is None:
        logger.error("Configuration (config) must be provided to create_record.")
        raise ValueError("Configuration is missing.")

    url = f"{config['baserow']['api_url']}{table_id}/"

    params = {"user_field_names": "true"}

    headers = get_baserow_headers()   

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers=headers,
            json=data,
            params=params
        ) as response:
            if response.status == 200:
                logger.success(f"Successfully created record {data} in table {table_id}")
                return await response.json()
            else:
                # Try to get error details from response
                try:
                    error_details = await response.text()
                except:
                    error_details = "No additional error details available"
                    
                logger.error(f"Failed to create record in table {table_id}. Status code: {response.status}")
                logger.error(f"Error details: {error_details}")
                
                # Specific handling for common issues
                if response.status == 403:
                    logger.error("403 Forbidden - Check your Baserow API token permissions")
                elif response.status == 400:
                    logger.error("400 Bad Request - Check your data format and field names")
                elif response.status == 401:
                    logger.error("401 Unauthorized - Check your Baserow API token")
                elif response.status == 413:
                    logger.error("413 Payload Too Large - Check if your data exceeds limits")
                    
                return None
        

async def get_rows(table_id, config, user_field_names=True, page=1, size=100, search=None, 
                  order_by=None, filters=None, filter_type='AND', include=None, 
                  exclude=None, view_id=None):
    """
    Get all rows from a Baserow table with pagination and filtering
    :param table_id: ID of the table to query
    :param config: The configuration dictionary
    :param user_field_names: Whether to use human-readable field names
    :param page: Page number to retrieve
    :param size: Number of rows per page
    :param search: Search query
    :param order_by: Field(s) to order by
    :param filters: Dictionary of filters
    :param filter_type: 'AND' or 'OR' for multiple filters
    :param include: Fields to include
    :param exclude: Fields to exclude
    :param view_id: View ID to apply
    :return: List of rows or None if failed
    """
    if config is None:
        logger.error("Configuration (config) must be provided to get_rows.")
        raise ValueError("Configuration is missing.")

    url = f"{config['baserow']['api_url']}{table_id}/"
    params = {
        "user_field_names": "true" if user_field_names else "false",
        "page": page,
        "size": size
    }
    
    # Add optional parameters
    if search:
        params['search'] = search
    if order_by:
        params['order_by'] = order_by
    if filters:
        params['filters'] = filters
        params['filter_type'] = filter_type
    if include:
        params['include'] = include
    if exclude:
        params['exclude'] = exclude
    if view_id:
        params['view_id'] = view_id

    if filters:
        # Convert filters to Baserow's expected format
        filter_params = {}
        for field, value in filters.items():
            filter_params[f"filter__{field}__equal"] = str(value)
        params.update(filter_params)
    headers = get_baserow_headers() 
    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"Successfully retrieved rows from table {table_id}")
                        return data['results']
                    else:
                        logger.error(f"Failed to get rows from table {table_id}. Status code: {response.status}")
                        if response.status < 500 and response.status != 429:
                            return None
            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/3 failed to get rows from {table_id}: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        return None
        
async def update_record(table_id, data_to_update, data, config):
    """
    Generic function to update a record in any Baserow table
    :param table_id: ID of the table containing the record
    :param data_to_update: Dictionary of fields to update
    :param data: Dictionary containing the flight data (used to find the record)
    :param config: The configuration dictionary
    :return: Updated record data or None if failed
    """
    if config is None:
        logger.error("Configuration (config) must be provided to update_record.")
        raise ValueError("Configuration is missing.")

    # Find the record to update
    row_data = await query_table(table_id, config, filters={'registration': data['registration']})
    
    # If no record found, we can't update it
    if row_data is None:
        logger.warning(f"No record found for registration {data['registration']} in table {table_id}. Cannot update.")
        return None
        
    row_id = row_data['id']
    url = f"{config['baserow']['api_url']}{table_id}/{row_id}/"

    params = {"user_field_names": "true"}
    headers = get_baserow_headers()
    
    max_retries = 5
    base_delay = 1  # Starting delay in seconds
    retry_count = 0
    
    async with aiohttp.ClientSession() as session:
        while retry_count < max_retries:
            try:
                async with session.patch(
                    url,
                    headers=headers,
                    json=data_to_update,
                    params=params
                ) as response:
                    if response.status == 200:
                        logger.success(f"Successfully updated record {data_to_update} from {data['registration']} in table {table_id}")
                        return await response.json()
                    elif response.status == 429:  # Rate limited
                        retry_after = int(response.headers.get('Retry-After', base_delay))
                        wait_time = min(retry_after * (2 ** retry_count), 60)  # Cap at 60 seconds
                        logger.warning(f"Rate limited. Retrying in {wait_time} seconds (attempt {retry_count + 1})")
                        await asyncio.sleep(wait_time)
                        retry_count += 1
                        continue
                    else:
                        # Try to get error details from response
                        try:
                            error_details = await response.text()
                        except:
                            error_details = "No additional error details available"
                            
                        logger.error(f"Failed to update record in table {table_id}. Status code: {response.status}")
                        logger.error(f"Error details: {error_details}")
                        
                        # Specific handling for common issues
                        if response.status == 403:
                            logger.error("403 Forbidden - Check your Baserow API token permissions")
                        elif response.status == 400:
                            logger.error("400 Bad Request - Check your data format and field names")
                        elif response.status == 401:
                            logger.error("401 Unauthorized - Check your Baserow API token")
                        elif response.status == 404:
                            logger.error("404 Not Found - Check if the record exists")
                        elif response.status == 413:
                            logger.error("413 Payload Too Large - Check if your data exceeds limits")
                            
                        return None
            except Exception as e:
                logger.error(f"Error updating record: {e}")
                if retry_count < max_retries - 1:
                    wait_time = base_delay * (2 ** retry_count)
                    logger.warning(f"Retrying in {wait_time} seconds (attempt {retry_count + 1})")
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                else:
                    logger.error(f"Max retries ({max_retries}) reached. Giving up.")
                    return None
        logger.error(f"Max retries ({max_retries}) reached. Failed to update record.")
        return None
        
async def get_all_rows_as_dict(table_id: int, config, key: str = "registration") -> dict:
    """Get all rows from a specified table and return as dictionary with registration as key"""
    if config is None:
        logger.error("Configuration (config) must be provided to get_all_rows_as_dict.")
        raise ValueError("Configuration is missing.")

    logger.info(f"Starting to get all rows from table {table_id}")
    page = 1
    all_rows = []
    
    while True:
        logger.debug(f"Fetching page {page} of table {table_id}")
        rows = await get_rows(table_id, config, page=page, size=100)
        if not rows:
            logger.warning(f"No more rows found in table {table_id} rows: {len(all_rows)}")
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            logger.debug(f"Last page of rows found in table {table_id}")
            break
        page += 1
    
    data_dict = {}
    logger.debug(f"Processing {len(all_rows)} rows into dictionary")
    
    processed_count = 0
    for row in all_rows:
        if key in row and row[key]:
            data_dict[row[key]] = row
            processed_count += 1
    logger.info(f"Processed {len(all_rows)} total rows, found {processed_count} valid entries with key '{key}'")
    if processed_count == 0:
        logger.error(f"No valid registrations found in table {table_id}")
    else:
        logger.success(f"Successfully created dict {table_id} {processed_count} entries from table {table_id}")
    
    return data_dict

async def get_cached_all_rows_as_dict(table_id: int, config, key: str = "registration", ttl_seconds: int = 300) -> dict:
    """Get all rows from a specified table with caching support"""
    return await get_cached_rows_as_dict(table_id, config, key, ttl_seconds)
