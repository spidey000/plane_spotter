import sys

file_path = 'readme.md'
search_text = """-   Comprehensive logging using Loguru.

## API Integrations"""

replace_text = """-   Comprehensive logging using Loguru.

## Documentation

Detailed documentation can be found in the `docs/` directory:

-   **Technical Documentation**: `docs/technical/`
    -   [Aircraft Tracking Logic](docs/technical/AIRCRAFT_TRACKING.md)
    -   [Cache System](docs/technical/CACHE_SYSTEM.md)
    -   [Database Schema](docs/technical/DATABASE_SCHEMA.md)
    -   [Error Handling](docs/technical/ERROR_HANDLING_PLAN.md)
    -   [Creating Social Plugins](docs/technical/creating_social_plugins.md)
-   **External Libraries**: `docs/external_libs/`
    -   [Bluesky Documentation](docs/external_libs/bluesky_documentation.md)
    -   [Twikit Documentation](docs/external_libs/twikit_documentation.md)
-   **Project History**: `docs/project_history/`
    -   [Changelog](docs/project_history/CHANGELOG.md)
    -   [Bugfix Summary](docs/project_history/BUGFIX_SUMMARY.md)

## API Integrations"""

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Normalize line endings just in case
content = content.replace('\r\n', '\n')
search_text = search_text.replace('\r\n', '\n')
replace_text = replace_text.replace('\r\n', '\n')

if search_text in content:
    new_content = content.replace(search_text, replace_text)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully updated readme.md")
else:
    print("Search text not found")
    idx = content.find("Comprehensive logging using Loguru.")
    if idx != -1:
        print(f"Found snippet: {content[idx:idx+100]!r}")
    else:
        print("Snippet not found")
