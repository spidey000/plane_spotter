# this is a script to manage the baserow database
# it will be used to store the flight airlines and aircraft models

# https://github.com/bram2w/baserow
# https://baserow.io/docs/index

import aiohttp
from loguru import logger
import datetime

# import the credentials for the baserow

# all registrations table '441094'
# all models table '441095'
# to check interesting models '441097'
# to check interesting registrations '441099'

# token 'CAMiafEgTCRDCcymT5FKH5inb3u2geKK'



#generate the authentication 
# Set up authentication headers for Baserow API
BASEROW_TOKEN = 'CAMiafEgTCRDCcymT5FKH5inb3u2geKK'
headers = {
    "Authorization": f"Token {'CAMiafEgTCRDCcymT5FKH5inb3u2geKK'}",
    "Content-Type": "application/json"
}
async def query_table(table_id, filters=None, user_field_names=True):
    """
    Generic function to query any Baserow table
    :param table_id: ID of the table to query
    :param filters: Dictionary of filters to apply
    :param user_field_names: Whether to use human-readable field names
    :return: Response data or None if not found
    """
    url = f"https://api.baserow.io/api/database/rows/table/{table_id}/"
    params = {"user_field_names": "true" if user_field_names else "false"}
    
    if filters:

        for field, value in filters.items():
            if isinstance(value, dict):
                # Extract value from filter dict if provided in advanced format
                value = value.get('value', '')
            params[f"filter__{field}__equal"] = str(value)
                
    async with aiohttp.ClientSession() as session:
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
                return None
        
async def query_registrations_table(flight):
    logger.debug(f"Querying registrations table for flight {flight['registration']}")
    return await query_table(
        table_id=441094,  # Registrations table ID
        filters={"registration": flight['registration']}
    )

async def query_interesting_registrations_table(flight):
    logger.debug(f"Querying interesting registrations table for flight {flight['registration']}")
    return await query_table(
        table_id=441099,  # Interesting registrations table ID
        filters={"registration": flight['registration']}
    )

async def query_interesting_models_table(flight):
    model = flight['aircraft_name']
    if model:
        logger.debug(f"Querying interesting models table for model {model}")
        model_query = await query_table(
            table_id=441097,  # Interesting models table ID
            filters={"name": model}
        )
        return model_query
    else:
        model = flight['aircraft_icao']
        logger.debug(f"Querying interesting models table for model {model}")
        model_query = await query_table(
            table_id=441097,  # Interesting models table ID
            filters={"model": model}
        )
        return model_query


async def create_record(table_id, data):
    """
    Generic function to create a record in any Baserow table
    :param table_id: ID of the table to create record in
    :param data: Dictionary of data to create
    :return: Created record data or None if failed
    """
    url = f"https://api.baserow.io/api/database/rows/table/{table_id}/"

    params = {"user_field_names": "true"}
    
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
            logger.error(f"Failed to create record in table {table_id}. Status code: {response.status}")
            return None
        

async def get_rows(table_id, user_field_names=True, page=1, size=100, search=None, 
                  order_by=None, filters=None, filter_type='AND', include=None, 
                  exclude=None, view_id=None):
    """
    Get all rows from a Baserow table with pagination and filtering
    :param table_id: ID of the table to query
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
    url = f"https://api.baserow.io/api/database/rows/table/{table_id}/"
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
        
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                logger.debug(f"Successfully retrieved rows from table {table_id}")
                return data['results']
            else:
                logger.error(f"Failed to get rows from table {table_id}. Status code: {response.status}")
                return None

async def update_record(table_id, data_to_update, data):
    """
    Generic function to update a record in any Baserow table
    :param table_id: ID of the table containing the record
    :param row_id: ID of the row to update
    :param data: Dictionary of fields to update
    :return: Updated record data or None if failed
    """

    row_id = await query_table(table_id, filters={'registration': data['registration']})
    url = f"https://api.baserow.io/api/database/rows/table/{table_id}/{row_id['id']}/"

    params = {"user_field_names": "true"}

    async with aiohttp.ClientSession() as session:
        async with session.patch(
            url,
            headers=headers,
            json=data_to_update,
            params=params
        ) as response:
            if response.status == 200:
                logger.success(f"Successfully updated record {data_to_update} from {data['registration']} in table {table_id}")
                return await response.json()
            logger.error(f"Failed to update record in table {table_id}. Status code: {response.status}")
            return None
        
async def get_all_rows_as_dict(table_id: int, key: str = "registration") -> dict:
    """Get all rows from a specified table and return as dictionary with registration as key"""
    logger.info(f"Starting to get all rows from table {table_id}")
    page = 1
    all_rows = []
    
    while True:
        logger.debug(f"Fetching page {page} of table {table_id}")
        rows = await get_rows(table_id, page=page, size=100)
        if not rows:
            logger.warning(f"No more rows found in table {table_id}")
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            logger.debug(f"Last page of rows found in table {table_id}")
            break
        page += 1
    
    registrations_dict = {}
    logger.debug(f"Processing {len(all_rows)} rows into dictionary")
    
    processed_count = 0
    for row in all_rows:
        if key in row and row[key]:
            registrations_dict[row[key]] = row
            processed_count += 1
    
    if processed_count == 0:
        logger.error(f"No valid registrations found in table {table_id}")
    else:
        logger.success(f"Successfully created dict {processed_count} entries from table {table_id}")
    
    return registrations_dict
