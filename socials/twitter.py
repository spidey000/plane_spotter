## for this handler you hace to use twikit library documentation avaliable in C:\Users\hp\Documents\CODE\twitter_spotter_v4\twikit_documentation.md
from . import socials_processing as sp
import utils.image_finder as image_finder
import asyncio
from twikit import Client
from datetime import timedelta

async def create_tweet(client, flight_data):
    client = Client()  # Initialize your Twikit client
    await client.login('username', 'password')
    """
    create a tweet using Twikit's built-in function
    async create_tweet(text: str = '', media_ids: list[str] | None = None, poll_uri: str | None = None, reply_to: str | None = None, conversation_control: Literal['followers', 'verified', 'mentioned'] | None = None, attachment_url: str | None = None, community_id: str | None = None, share_with_followers: bool = False, is_note_tweet: bool = False, richtext_options: list[dict] = None, edit_tweet_id: str | None = None)→ Tweet

    """


    USERNAME = 'example_user'
    EMAIL = 'email@example.com'
    PASSWORD = 'password0000'

    # Initialize client
    client = Client('en-US')

    async def main():
        await client.login(
            auth_info_1=USERNAME,
            auth_info_2=EMAIL,
            password=PASSWORD,
            cookies_file='cookies.json'
        )

    asyncio.run(main())
    #Create a tweet with media attached.

    # Upload media files and obtain media_ids
    media_ids = [
        await client.upload_media('media1.jpg'),
        await client.upload_media('media2.jpg')
    ]

    # Create a tweet with the provided text and attached media
    await client.create_tweet(
        text='Example Tweet',
        media_ids=media_ids
    )
