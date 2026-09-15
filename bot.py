# Written by EnvyingGolem47
# 4/15/2026
#
# Python Marketplace Discord Bot - Built for Project Nebula
#
# Updated: 9/9/2026 - EnvyingGolem47

import datetime
import time
import re
from json import JSONDecodeError
import io
import os
import copy
import hashlib

import chat_exporter
import discord
from discord.ext import tasks, commands
from superutilities import SInput, SanitizeString, getJsonFromFile, saveJsonToFile, Logger
import mysql.connector
import paramiko

image_folder = "data/images/"
memory_folder = "system/memory/"
logs_folder = "data/logs/"
# The system folder should already be there, as the files in it are not meant to be deleted, modified, or moved by the user
variables_file = "data/.variables.json"
district_role_mappings_file = f"{memory_folder}district_role_mappings.json"
sql_template_file = f"system/sql_template.sql"

# Designed to just accept baguette bot's baguette_config.json file
emoji_to_staff_member_file = "data/baguette_config.json"

logger = Logger(logs_folder)
logger.log("==== BOT STARTING UP ====")

forbidden_name = re.compile(r"🗒-district-[0-9]+-comments", re.IGNORECASE)
district_regex = re.compile(r"District [0-9]+")
ticket_regex = re.compile(r"ticket-[0-9]+-\S*", re.IGNORECASE)

# Set to true if you want your console to be unreadable (Or if you are genuinely working on the bot)
debug_mode = False

# General Todo list
# TODO: Optimize code once finished with all features of it (surely this will happen)
# TODO: Change all owner embeds to create new field when reaching 1024 character limit in the value section. (up to 20 fields, 6000 character limit must be maintained 0-0)
# TODO: Update how districts are handled to allow the use of shop counts. And also find an optimized way of counting the shops rather than an sql query or api call.
# TODO: Remove all DEV Commands, and Stopwatches when done
# TODO: Final decision on logger

# The shop_ticket_process dictionary is how the bot goes through and runs the shop creation process.
#  I made it this way to help maintain reliability within a shop creation ticket. Even if the bot goes offline or breaks, it can be easily recovered, without starting over.
#  If the bot doesn't respond/is offline when you send a message, delete your message and try again. (same thing with reactions)
#  This was one of the first things I worked on, cause I really want the shop creation process to be recoverable from any point during it.
#
# MESSAGE - Expects a message response
# REACTION_YES_OR_NO - Expects a reaction of either Yes or No emojis
# REACTION_CHECKMARK - Expects a reaction of a :white_check_mark: emoji
# NONE - Expects nothing
# IMAGE - Expects Image

# <USER> - replaced with the user that created the ticket - NOTE: Don't actually use this one
# <LAST_MESSAGE> - replaced with the last message the user sent

# response_type is the type of response expected (see above list) ^
# message_regex (The second item in the list) is the regex that matches the question.
# response_regex is the regex that the answer is expected to match ( ANY bypasses the check ) ( NUMBER will use .isdigit instead )
# yes_response (for REACTION_YES_OR_NO & REACTION_CHECKMARK) determines the sub process triggered for a YES ( NORMAL proceeds with main ticket process )
# no_response (for REACTION_YES_OR_NO) determines the sub process triggered for a NO ( NORMAL proceeds with main ticket process )
# stored_variable is the variable the response will be stored in
shop_ticket_process = \
    {
        "Hi, <USER>! Let's create a shop! What is your shop's name?":
            {"response_type":'MESSAGE',
             "message_regex":r"Hi, \S*! Let's create a shop! What is your shop's name\?",
             "response_regex":r"ANY",
             "stored_variable":"shop_name"},

        "Great! We will name this shop <LAST_MESSAGE>. Where is this shop located? X Y Z format, please!":
            {"response_type":'MESSAGE',
             "message_regex":r"Great! We will name this shop [\S\s]*\. Where is this shop located\? X Y Z format, please!",
             "response_regex":r"-?[0-9]* -?[0-9]* -?[0-9]*",
             "stored_variable":"shop_coords"},

        "<LAST_MESSAGE> is a fabulous location! Who owns this shop? Minecraft IGN, please!":
            {"response_type":'MESSAGE',
             "message_regex":r"\S* \S* \S* is a fabulous location! Who owns this shop\? Minecraft IGN, please!",
             "response_regex":r"ANY",
             "stored_variable":"owners_mc_list"},

        "<LAST_MESSAGE>, cool. Hey, what's their Discord Username OR Discord ID?":
            {"response_type":'MESSAGE',
             "message_regex":r"\S*, cool\. Hey, what's their Discord Username OR Discord ID\?",
             "response_regex":r"ANY",
             "stored_variable":"owners_discord_list"},

        '<LAST_MESSAGE>, got it! Are there any additional owners? React :regional_indicator_y: for "Yes", or :regional_indicator_n: for "No".':
            {"response_type":'REACTION_YES_OR_NO',
             "message_regex":r'\S*, got it! Are there any additional owners\? React :regional_indicator_y: for "Yes", or :regional_indicator_n: for "No"\.',
             "response_regex":r"ANY",
             "yes_response":"Another owner? Cool, what's their Minecraft IGN?",
             "no_response":"NORMAL",
             "stored_variable":"NONE"},

        'Has this shop been added to the GUI Marketplace Directory? React :regional_indicator_y: for "Yes", or :regional_indicator_n: for "No".':
            {"response_type":'REACTION_YES_OR_NO',
             "message_regex":r'Has this shop been added to the GUI Marketplace Directory\? React :regional_indicator_y: for "Yes", or :regional_indicator_n: for "No"\.',
             "response_regex":r"ANY",
             "yes_response":"NORMAL",
             "no_response":"Oh no! Please contact the owner(s) and ask them to add their shop to a GUI Marketplace Directory! (React with a ✅ when it has been added)",
             "stored_variable":"initialized"},

        'Perfect! Is this a large and/or tall shop? React, please!':
            {"response_type":'REACTION_YES_OR_NO',
             "message_regex":r'Perfect! Is this a large and\/or tall shop\? React, please!',
             "response_regex":r"ANY",
             "yes_response":"NORMAL",
             "no_response":"NORMAL",
             "stored_variable":"large_shop"},

        'Okay! Is this a service shop? React, please!':
            {"response_type":'REACTION_YES_OR_NO',
             "message_regex":r'Okay! Is this a service shop\? React, please!',
             "response_regex":r"ANY",
             "yes_response":"NORMAL",
             "no_response":"NORMAL",
             "stored_variable":"service_shop"},

        'Can you grab ONE photo of the shop for me? I accept .jpg, .jpeg, .png., and .gif filetypes. Post it here ;)':
            {"response_type":'IMAGE',
             "message_regex":r"Can you grab ONE photo of the shop for me\? I accept \.jpg, \.jpeg, \.png\., and \.gif filetypes\. Post it here ;\)",
             "response_regex":r"ANY",
             "stored_variable":"shop_image_url"},

        'Thanks! Last thing! Send the district number this shop belongs in!':
            {"response_type":'MESSAGE',
             "message_regex":r'Thanks! Last thing! Send the district number this shop belongs in!',
             "response_regex":r"NUMBER",
             "stored_variable":"district_number"}
    }

# Same thing as the above, but is how stuff like additional owners, and answering no on some questions work
# main_process_key is the key that the system looks for to drive the process back into the main ticket process dictionary
sub_ticket_process = \
    {
        'Oh no! Please contact the owner(s) and ask them to add their shop to a GUI Marketplace Directory! (React with a ✅ when it has been added)':
            {"response_type":'REACTION_CHECKMARK',
             "message_regex":r'Oh no! Please contact the owner\(s\) and ask them to add their shop to a GUI Marketplace Directory! \(React with a ✅ when it has been added\)',
             "response_regex":r"ANY",
             "yes_response":"Perfect! Is this a large and/or tall shop? React, please!",
             "stored_variable":"initialized"},

        "Another owner? Cool, what's their Minecraft IGN?":
            {"response_type":'MESSAGE',
             "message_regex":r"Another owner\? Cool, what's their Minecraft IGN\?",
             "response_regex":r"ANY",
             "main_process_key":"<LAST_MESSAGE>, cool. Hey, what's their Discord Username OR Discord ID?",
             "stored_variable":"owners_mc_list"}
    }

# This template is to help maintain consistency with the shop embeds without repeating it at every corner.
shop_embeds_template = \
    [
        {
            "image": {
                "url": "<shop_image_url>"
            },
            "fields": [
                {
                    "name": "Owners: ",
                    "value": "<shop_owners_list>",
                    "inline": False
                },
                {
                    "name": "Initialized: ",
                    "value": "<initialized>",
                    "inline": True
                },
                {
                    "name": "Large Shop: ",
                    "value": "<large_shop>",
                    "inline": True
                },
                {
                    "name": "Service Shop: ",
                    "value": "<service_shop>",
                    "inline": True
                }
            ],
            "color": 3447003,
            "type": "rich",
            "title": "<shop_name> (<shop_coords>)"
        },
        {
            "fields": [
                {
                    "name": "\u2705: OK",
                    "value": "Shop active\uff5c",
                    "inline": True
                },
                {
                    "name": "\u26a0\ufe0f: Warning",
                    "value": "Owner Contacted\uff5c",
                    "inline": True
                },
                {
                    "name": "\u274c: Reclaim",
                    "value": "Shop inactive",
                    "inline": True
                }
            ],
            "color": 10181046,
            "type": "rich",
            "title": "Shop Check Legend"
        },
        {
            "fields": [
                {
                    "name": "Status:",
                    "value": "<status>",
                    "inline": False
                },
                {
                    "name": "Next check due:",
                    "value": "<next_check>",
                    "inline": False
                },
                {
                    "name": "Last checked by:",
                    "value": "<last_checked_by> on <last_checked>",
                    "inline": False
                }
            ],
            "color": 10181046,
            "type": "rich",
            "title": "Shop Status"
        },
        {
            "fields": [
                {
                    "name": "Copy:",
                    "value": "<shop_check_commands>",
                    "inline": False
                }
            ],
            "color": 10181046,
            "type": "rich",
            "title": "Shop Check Command"
        }
    ]

class DatabaseHandler:
    def __init__(self,url:str,database_name:str,username:str,password:str,port:int):
        """
        Initializes, stores, and handles the connection to the SQL database.

        :param url: HOSTNAME
        :param database_name: DATABASE_NAME
        :param username: USERNAME
        :param password: PASSWORD
        :param port: PORT
        """
        self.url = url
        self.database_name = database_name
        self.username = username
        self.password = password
        self.port = port
        self.connection = mysql.connector.connect(host=self.url,database=self.database_name,user=self.username,password=self.password,port=self.port,autocommit=True)
        self.query_queue = []

    def connect_to_database(self):
        self.connection = mysql.connector.connect(host=self.url, database=self.database_name, user=self.username,
                                                  password=self.password, port=self.port, autocommit=True)

    def query(self,query):
        """
        Runs an SQL query against the database.
        The format it returns the query in is a little strange. Most of the time putting [0][0] after this function works just fine.

        :param query:
        :return:
        """
        if not self.connection.is_connected():
            self.connect_to_database()

        cursor = self.connection.cursor(buffered=True)
        cursor.execute(query)
        return cursor.fetchall()

    def query_script(self,file_path):
        """
        Similar to query, but runs an .sql script file.

        For some reason this will disconnect you from the database, so you MUST reconnect afterwards. (No, I do not know why)

        :param file_path:
        :return:
        """
        cursor = self.connection.cursor(buffered=True)
        file = open(file_path,'r')
        file_data = file.read()
        cursor.execute(file_data)
        return cursor.fetchall()

    def queue_query(self,query:str):
        """
        Queue up queries to run later. (Goal: keep the queue as empty as possible.)
        INSERT AND UPDATE QUERIES ONLY. THIS DOES NOT RETURN ANYTHING

        :param query:
        :return:
        """
        self.query_queue.append(query)

    def process_query_queue(self):
        """
        Runs all queries in the queue.

        :return:
        """
        for q in self.query_queue:
            try:
                self.query(q)
            except Exception as e:
                logger.log(f"Failed to execute queued query: {q}\n{e}", "[ERROR] ")

    def verify_format(self):
        """
        This is intended to be ran at startup to ensure the database is functioning and is in the correct format.
        # TODO: Only really need to run once. (Maybe query to check if everything is in place first?)

        :return:
        """

        # Verify all tables exist
        self.query_script(sql_template_file)

        # Reconnect cause it dies here for some reason
        self.connect_to_database()

        # Check if new owner lists exist in the shops table
        check_mc_owners = self.query("SHOW COLUMNS FROM shops LIKE 'mc_owners';")
        check_discord_owners = self.query("SHOW COLUMNS FROM shops LIKE 'discord_owners';")

        if len(check_mc_owners) <= 0:
            self.query("ALTER TABLE shops ADD mc_owners TEXT(802) NULL;")

        if len(check_discord_owners) <= 0:
            self.query("ALTER TABLE shops ADD discord_owners TEXT(1608) NULL;")

        # Check if the new date and time column exists if not then create it
        check_datetime_checks = self.query("SHOW COLUMNS FROM shop_checks LIKE 'date_and_time';")
        if len(check_datetime_checks) <= 0:
            self.query("ALTER TABLE shop_checks ADD date_and_time DATETIME NULL;")

        # Remove the auto increment statement from SQL, the incrementing is to be done inside the bot itself.
        self.query("ALTER TABLE shops MODIFY shop_id INT NOT NULL;")
        self.query("ALTER TABLE shop_checks MODIFY shop_id INT DEFAULT NULL;")

        # Dramatically increase the character limit for image URLs. Who knows how big discord ones will get in the future (hold the crafter).
        self.query("ALTER TABLE shops MODIFY image VARCHAR(4096) NULL;")

        # Increase character limit for shop name
        self.query("ALTER TABLE shops MODIFY shop_name VARCHAR(256) NULL;")

        # Increase character limit for shop coordinates
        self.query("ALTER TABLE shops MODIFY coords VARCHAR(256) NULL;")

        # Increase character limit for shop channel ids
        self.query("ALTER TABLE shops MODIFY shop_channel_id VARCHAR(256) NULL;")

        # Increase character limit for checked by ids
        self.query("ALTER TABLE shop_checks MODIFY checked_by_id VARCHAR(256) NULL;")

        # Increase character limit for timestamp
        self.query("ALTER TABLE shop_checks MODIFY timestamp VARCHAR(256) NULL;")

# ======================== FOR DEBUGGING ONLY ========================
class Stopwatch:
    def __init__(self,label:str):
        """
        No like seriously remove all instances of this once not using. It'll cause lag and clog up the console even more.

        :param label:
        """
        self.start_time = None
        self.end_time = None
        self.label = label

    def start(self,label:str=None):
        self.start_time = datetime.datetime.now()

        if label is not None:
            self.label = label

    def stop(self):
        self.end_time = datetime.datetime.now()
        debug(f"{self.label} : {self.end_time - self.start_time}")

# Just a small function to allow quick toggling of debug focused print statements. Look for debug_mode variable
def debug(txt:str):
    """
    When debug variable is true, this will print to the console.
    Surely leaving these around won't slow anything down. Surely.

    :param txt:
    :return:
    """
    if debug_mode:
        print(txt)

def get_next_check_deadline():
    """
    Returns the next deadline to check shops.

    :return datetime. int | bool:
    """

    # TODO: Change to determine if it's a Friday, Saturday, or Sunday, and then skip to next Sunday. (maybe difference in weekday # + 7?)
    # Monday  Tuesday  Wednesday  Thursday  Friday  Saturday  Sunday
    # 0       1        2          3         4       5         6

    current_datetime = datetime.datetime.now()
    new_datetime = datetime.datetime(year=current_datetime.year,month=current_datetime.month,day=current_datetime.day,hour=17)

    if 6 > current_datetime.weekday() >= 4:
        new_datetime = new_datetime + datetime.timedelta(days=7 + 6-current_datetime.weekday())
    elif current_datetime.weekday() == 6:
        new_datetime = new_datetime + datetime.timedelta(days=7)
    else:
        new_datetime = new_datetime + datetime.timedelta(days=6 - current_datetime.weekday())

    return int(new_datetime.timestamp())

def get_current_discord_timecode():
    """
    Returns the current time in a discord appropriate timecode.

    :return int:
    """
    current_datetime = datetime.datetime.now()
    return int(current_datetime.timestamp())

def check_directories():
    """
    Checks to make sure all directories are present.

    :return:
    """
    for d in [image_folder,memory_folder,logs_folder]:
        try:
            os.mkdir(d)

        except FileExistsError:
            pass

        except PermissionError:
            logger.log("UNABLE TO CREATE DIRECTORIES - INVALID PERMISSIONS","[CRITICAL] ")
            input("Press enter to close:")
            raise KeyboardInterrupt

def get_variables() -> dict:
    """
    Retrieves the data in variables.json, or if it doesn't exist, create and fill in a new one.

    :return:
    """
    try:
        variables_data = getJsonFromFile(variables_file)

        if len(variables_data.keys()) < 18:
            raise FileNotFoundError

    except FileNotFoundError:
        logger.log("COULD NOT FIND/LOAD VARIABLES FILE!", tag="[CRITICAL] ")
        print("Please follow these prompts to create a new one.")

        token = SInput("Please enter your bot token: ")
        guild_id = SInput("Please enter your Discord server's ID: ", IsInt=True)
        ticket_category_id = SInput("Please enter the category ID where you want Shop Tickets to be created in: ", IsInt=True)
        images_channel_id = SInput("Please enter the channel ID where you want Shop Images to be stored: ", IsInt=True)
        transcript_channel_id = SInput("Please enter the channel ID where you want Shop Transcripts to be stored: ", IsInt=True)
        shop_admin_id = SInput("Please enter the Shop Admin Role ID: ", IsInt=True)
        shop_staff_id = SInput("Please enter the Staff Role ID: ", IsInt=True)

        sql_hostname = SInput("Please enter your SQL Server's Hostname: ")
        sql_database_name = SInput("Please enter your SQL Server's Database name: ")
        sql_username = SInput("Please enter your SQL Server's Username: ")
        sql_password = SInput("Please enter your SQL Server's Password: ")
        sql_port = SInput("Please enter your SQL Server's Port Number: ",IsInt=True)

        sftp_hostname = SInput("Please enter your SQL Server's Hostname: ")
        sftp_username = SInput("Please enter your SQL Server's Username: ")
        sftp_password = SInput("Please enter your SQL Server's Password: ")
        sftp_port = SInput("Please enter your SQL Server's Port Number: ",IsInt=True)
        sftp_image_directory = SInput("Please enter the directory where your images are being stored in the SFTP server: ")
        image_url_prefix = SInput("Please enter the URL Prefix for where images are being hosted.\n(Example: 'test.com/image.png' you would put 'test.com/')\n: ")

        variables_data = \
            {
                "token": token,
                "guild_id": guild_id,
                "ticket_category_id":ticket_category_id,
                "images_channel_id": images_channel_id,
                "transcript_channel_id": transcript_channel_id,
                "shop_admin_id": shop_admin_id,
                "shop_staff_id": shop_staff_id,
                "sql_hostname": sql_hostname,
                "sql_database_name": sql_database_name,
                "sql_username": sql_username,
                "sql_password": sql_password,
                "sql_port": sql_port,
                "sftp_hostname": sftp_hostname,
                "sftp_username": sftp_username,
                "sftp_password": sftp_password,
                "sftp_port": sftp_port,
                "sftp_image_directory": sftp_image_directory,
                "image_url_prefix": image_url_prefix
            }

        saveJsonToFile(variables_file,variables_data)

        logger.log("Variables file created.", tag="[INFO] ")

    return variables_data

def load_emojis():
    """
    Loads the baguette bot emojis.

    :return:
    """
    try:
        return getJsonFromFile(emoji_to_staff_member_file)["ticket_emoji"]
    except FileNotFoundError:
        logger.log(f"{emoji_to_staff_member_file} was not found. Creating blank one...", "[ERROR] ")
        saveJsonToFile(emoji_to_staff_member_file,{"ticket_emoji":{}})
        return {"ticket_emoji":{}}

def load_district_role_mappings():
    """
    This loads district_role_mappings into actual memory. It links each district to their respective roles.

    :return:
    """
    try:
        return getJsonFromFile(district_role_mappings_file)
    except FileNotFoundError or JSONDecodeError:
        logger.log("District Role Mappings not found, please use the map_district_role command to map all roles to their appropriate district.", tag="[WARN] ")
        saveJsonToFile(district_role_mappings_file,{})
        return {}

logger.log("Loading variables...", tag="[INFO] ")
check_directories()
variables = get_variables()
emoji_dict = load_emojis()
district_role_mappings = load_district_role_mappings()
logger.log("Connecting to Database...", tag="[INFO] ")
database = DatabaseHandler(
    variables["sql_hostname"],
    variables["sql_database_name"],
    variables["sql_username"],
    variables["sql_password"],
    variables["sql_port"]
)

database.verify_format()
logger.log("Connected and verified.", tag="[INFO] ")
logger.log("Loading Bot...", tag="[INFO] ")

def get_district_number(category_name:str) -> int:
    """
    Returns the number that a District category is.

    :param category_name:
    :return:
    """
    if district_regex.fullmatch(category_name):
        try:
            return int(category_name.replace("District ","").strip())
        except TypeError or AttributeError:
            return None
    else:
        return None

def construct_shop_embeds(embeds_template_og:list[dict],shop_info:dict):
    """
    Constructs the embeds for a shop.

    :param embeds_template_og: Just use shop_embeds_template unless told otherwise.
    :param shop_info:
    :return:
    """

    embeds_template = copy.deepcopy(embeds_template_og)

    new_embed_list = []

    owners_string = ""
    shop_check_command_string = ""

    for i, owner in enumerate(shop_info['owners_mc_list']):

        # Check to make sure the owners list doesn't go over discord's limit for embeds
        if len(owners_string) + len(f"{owner} (`{shop_info['owners_discord_list'][i]}`)\n") < 1024:
            owners_string += f"{owner} (`{shop_info['owners_discord_list'][i]}`)"

            debug(f"Service shop: {shop_info['service_shop']}")

            # Check to make sure the next added shop check won't go over the discord limit for embeds
            if len(shop_check_command_string) + len(f"```/co l time:2w action:container radius:10 user:{owner}```") < 1024:
                if shop_info['service_shop'] is False or shop_info['service_shop'] == "False":
                    shop_check_command_string += f"```/co l time:2w action:container radius:10 user:{owner}```"

                else:
                    shop_check_command_string += f"```/co l time:4w action:+session user:{owner}```"

                if len(shop_info['owners_mc_list']) != i + 1:
                    shop_check_command_string += '\n'

            if len(shop_info['owners_mc_list']) != i + 1:
                owners_string += '\n'

    shop_info['shop_owners_list'] = owners_string
    shop_info['shop_check_commands'] = shop_check_command_string

    def parse_requested_variables(text:str):
        variables_list = []

        temp = re.split(r"[^>]*<",text)

        for t in temp:
            if len(t) > 0:
                variables_list.append(re.split(r">", t)[0])


        return variables_list


    def value_dive(d:dict):
        for k in d:
            if type(d[k]) == dict:
                value_dive(d[k])
            elif type(d[k]) == str:
                debug(f"Value Dive: {d[k].count('<') + d[k].count('>')}")
                if d[k].count('<') + d[k].count('>') >= 2:
                    requested_variables = parse_requested_variables(d[k])
                    for variable in requested_variables:
                        try:
                            d[k] = d[k].replace(f'<{variable}>',f'{shop_info[variable]}')
                        except KeyError:
                            pass

            elif type(d[k]) == list:
                for n in d[k]:
                    if type(n) == dict:
                        value_dive(n)
            else:
                continue

    debug(f"embed templates length: {len(embeds_template)}")
    for embed_dict in embeds_template:

        value_dive(embed_dict)

        new_embed_list.append(discord.Embed().from_dict(embed_dict))
        debug(str(embed_dict))

    return new_embed_list

def get_next_id() -> int:
    """
    Returns the next ID. Autoincrements.

    :return:
    """

    # TODO: Keep in sync with SQL Data (Maybe? Might not be needed)
    try:
        result = database.query("SELECT MAX(shop_id) FROM shops;")
        return int(result[0][0]) + 1
    except Exception as e:
        logger.log(f"Failed to query max shop ids - {e}","[ERROR] ")

    try:
        counter = int(open(f'{memory_folder}counter', 'r').read())
        open(f'{memory_folder}counter', 'w').write(f'{counter+1}')
    except FileNotFoundError:
        counter = 0
        open(f'{memory_folder}counter', 'w').write(f'{counter}')

    return counter

def update_shop_check_command_embed(old_embed:discord.Embed, shop_channel_id:int, is_service_shop:bool) -> discord.Embed:
    """
    Easily update the embed with the shop check commands.

    :param old_embed:
    :param shop_channel_id:
    :param is_service_shop:
    :return:
    """
    owners = database.query(f"SELECT mc_owners FROM shops WHERE shop_channel_id = {shop_channel_id};")[0][0].split('|')

    shop_check_command_string = ""

    for i, field in enumerate(old_embed.fields):
        old_embed.remove_field(i)

    for i, owner in enumerate(owners):
        if owner == "":
            continue

        if len(owner) + 46 >= 1024:
            break

        if i != 0 and len(owners) -1 != i:
            shop_check_command_string += '\n'

        if not is_service_shop:
            shop_check_command_string += f"```/co l time:2w action:container radius:10 user:{owner}```" # 46 + owner

        else:
            shop_check_command_string += f"```/co l time:4w action:+session user:{owner}```"

    old_embed.add_field(name="Copy: ", value=shop_check_command_string, inline=False)

    return old_embed

# Loads the bot
bot = discord.Bot(intents=discord.Intents.all())

# Stores the Guild Object for later use
primary_guild = discord.Guild

# Async Functions
async def store_image(guild,attachment:discord.Attachment):
    """
    Saves the shop's image and returns the URL which it is stored at.

    :param guild:
    :param attachment:
    :return:
    """

    # TODO: Discord trick didn't work out too well, so SFTP with a Website server it is! :)
    # TODO: Maybe check if image already exists, but since its the hash as the name i dont see any major problems with just not checking (famous last words)

    await attachment.save(attachment.filename)
    debug("Saving to sftp server")

    raw_file = open(attachment.filename,'rb').read()
    hash_object = hashlib.sha256(raw_file)

    file_extension = attachment.filename.split(".")[-1]

    sha256_hash = hash_object.hexdigest()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # Apparently this isn't secure according to the docs, sooooo dont know what to do about that (not sure if it matters)

    ssh.connect(hostname=variables["sftp_hostname"], username=variables["sftp_username"], password=variables["sftp_password"],
                port=variables["sftp_port"])

    sftp = ssh.open_sftp()

    remote_file_path = f'{variables["sftp_image_directory"]}{sha256_hash}.{file_extension}'
    sftp.put(attachment.filename, remote_file_path)

    stored_url = f"{variables['image_url_prefix']}{sha256_hash}.{file_extension}"

    sftp.close()
    ssh.close()

    debug("Removing image")
    os.remove(attachment.filename)

    logger.log(f"Stored new image: '{stored_url}' in SFTP server.","[INFO] ")
    return stored_url

async def notify_district(district_number:int,msg:str,channel_list) -> bool:
    # TODO: FINISH
    # TODO: DO NOT USE RIGHT NOW, NEEDS SOME MORE TWEAKING TO MAKE WORTH HAVING IT

    if "<DISTRICT_ROLE>" in msg:
        msg.replace("<DISTRICT_ROLE>",f"<@&{district_role_mappings[district_number]}>")

    district_comments = None

    for channel in channel_list:
        if channel.name == f"🗒-district-{district_number}-comments":
            district_comments = channel

    if district_comments is None:
        return False

    try:
        await district_comments.send(msg)
    except KeyError:
        logger.log(f"No role mapped for District {district_number}", tag="[WARN] ")
    except AttributeError:
        logger.log(f"Comments channel for District {district_number} was not found.", tag="[ERROR] ")

    return True

async def create_shop_channel(ticket_channel:discord.TextChannel,premade_shop_info=None,shop_already_in_database:bool=False) -> bool | None:

    # guild = await bot.fetch_guild(variables["guild_id"])

    # If using the normal ticket process
    if ticket_channel is not None and premade_shop_info is None:
        # List of process keys, so I didn't have to do this every line
        shop_ticket_process_keys = set(shop_ticket_process.keys())
        sub_ticket_process_keys = set(sub_ticket_process.keys())

        # TODO: 1- get list of messages
        msg_list = []
        shop_info = {}

        async for message in ticket_channel.history(oldest_first=True):
            msg_list.append(message)

        # TODO: 2- read messages and compare with shop/sub ticket processes
        # TODO: 3- store all data in respective spaces
        # TODO: 4- Send shop image in image channel
        # TODO: 5- Replace shop_image_url with image url in the image channel


        for i, msg in enumerate(msg_list):
            found_match = False
            for k in shop_ticket_process_keys:
                if re.compile(shop_ticket_process[k]['message_regex']).fullmatch(msg.content) and shop_ticket_process[k]['response_type'] in ["MESSAGE","IMAGE"]:

                    if '_list' in shop_ticket_process[k]['stored_variable']:
                        if shop_ticket_process[k]['stored_variable'] in shop_info.keys():
                            shop_info[shop_ticket_process[k]['stored_variable']].append(msg_list[i+1].content)
                        else:
                            shop_info[shop_ticket_process[k]['stored_variable']] = [msg_list[i+1].content]

                    else:
                        if shop_ticket_process[k]['response_type'] == 'IMAGE':
                            shop_info[shop_ticket_process[k]['stored_variable']] = await store_image(ticket_channel.guild,msg_list[i + 1].attachments[0])
                        else:
                            shop_info[shop_ticket_process[k]['stored_variable']] = msg_list[i+1].content

                    found_match = True
                    break

                elif re.compile(shop_ticket_process[k]['message_regex']).fullmatch(msg.content) and shop_ticket_process[k]['response_type'] in ["REACTION_YES_OR_NO"]:
                    #if msg.reactions[0].emoji in ['🇳','❌',':regional_indicator_n:',':x:']:
                    if msg.reactions[1].count > 1:
                        shop_info[shop_ticket_process[k]['stored_variable']] = False
                    #elif msg.reactions[0].emoji in ['✅','🇾',':white_check_mark:',':regional_indicator_y:']:
                    elif msg.reactions[0].count > 1:
                        shop_info[shop_ticket_process[k]['stored_variable']] = True

                    found_match = True
                    break

            if not found_match:
                for k in sub_ticket_process_keys:
                    if re.compile(sub_ticket_process[k]['message_regex']).fullmatch(msg.content) and sub_ticket_process[k]['response_type'] in ["MESSAGE","IMAGE"]:

                        if '_list' in sub_ticket_process[k]['stored_variable']:
                            if sub_ticket_process[k]['stored_variable'] in shop_info.keys():
                                shop_info[sub_ticket_process[k]['stored_variable']].append(msg_list[i + 1].content)
                            else:
                                shop_info[sub_ticket_process[k]['stored_variable']] = [msg_list[i + 1].content]

                        else:
                            if sub_ticket_process[k]['response_type'] == 'IMAGE':
                                shop_info[sub_ticket_process[k]['stored_variable']] = await store_image(ticket_channel.guild, msg_list[i + 1].attachments[0])
                            else:
                                shop_info[sub_ticket_process[k]['stored_variable']] = msg_list[i + 1].content

                        found_match = True
                        break

                    elif re.compile(sub_ticket_process[k]['message_regex']).fullmatch(msg.content) and sub_ticket_process[k][
                        'response_type'] in ["REACTION_YES_OR_NO"]:

                        #if msg.reactions[0].emoji in ['🇳', '❌', ':regional_indicator_n:', ':x:']:
                        if msg.reactions[1].count > 1:
                            shop_info[sub_ticket_process[k]['stored_variable']] = False

                        #elif msg.reactions[0].emoji in ['✅', '🇾', ':white_check_mark:', ':regional_indicator_y:']:
                        elif msg.reactions[0].count > 1:
                            shop_info[sub_ticket_process[k]['stored_variable']] = True

                        found_match = True
                        break

            debug(f'{msg.content}\nMatch?: {found_match}')

        temp_1 = get_current_discord_timecode()
        temp_2 = get_next_check_deadline()

        shop_info['status'] = "✅ OK"
        shop_info['next_check'] = f"<t:{temp_2}:f>" # <t:1776276900:f>
        shop_info['last_checked_by'] = f"<@{msg_list[-1].author.id}>"
        shop_info['last_checked'] = f"<t:{temp_1}:f>"

        shop_info['sql_id'] = get_next_id()

    # If using premade shop info
    if premade_shop_info is not None:
        shop_info = premade_shop_info # copy.deepcopy(premade_shop_info)
        # debug(f"Deep copied {shop_info['shop_name']}")
        # shop_info = premade_shop_info

        temp_1 = get_current_discord_timecode()
        temp_2 = get_next_check_deadline()

        if shop_already_in_database:

            # TODO: Possibly don't include if we're starting over with a blank slate.
            # TODO: Actually if we do start over with a blank slate, lets make all new records that have the okay status for the shops

            last_check = database.query(f"SELECT shop_status, checked_by_id, date_and_time FROM shop_checks WHERE shop_id = {shop_info['sql_id']}")[0]

            shop_info['status'] = f"{last_check[0]}"
            shop_info['next_check'] = f"<t:{temp_2}:f>"  # <t:1776276900:f>
            shop_info['last_checked_by'] = f"<@{last_check[1]}>"
            shop_info['last_checked'] = f"<t:{int(last_check[2].timestamp())}:f>"

        else:
            shop_info['status'] = "✅ OK"
            shop_info['next_check'] = f"<t:{temp_2}:f>"  # <t:1776276900:f>
            shop_info['last_checked_by'] = f"<@{bot.user.id}>"
            shop_info['last_checked'] = f"<t:{temp_1}:f>"

    # TODO: 6- Trigger construct_shop_embeds with stored data
    embed_list = construct_shop_embeds(shop_embeds_template,shop_info)

    # TODO: 7- Check if district category exists (if not create it)
    category_id = None
    new_category = None
    district_comments = None
    guild_channels = await primary_guild.fetch_channels()
    guild_categories = []

    for channel in guild_channels:
        if type(channel) == discord.CategoryChannel:
            guild_categories.append(channel)

        if channel.name == f"🗒-district-{shop_info['district_number']}-comments":
            district_comments = channel

    debug("Checking categories")
    debug(f"{guild_categories}")
    for cat in guild_categories:

        debug(f"Checking {cat.name}...")
        if get_district_number(cat.name) == int(shop_info['district_number']):
            debug("Found District match")
            category_id = cat.id
            break

    # TODO: SANITIZE SHOP NAME HERE
    shop_info['shop_name'] = SanitizeString(shop_info['shop_name'],bannedCharacters=['$', '&', '{', '}', '\\', '/', '[', ']','(',')','|','<','>'])


    # Create owner strings to upload into the SQL Database
    mc_owners_list_str = ""
    discord_owners_list_str = ""

    for i, m in enumerate(shop_info['owners_mc_list']):
        if i < len(shop_info['owners_mc_list'])-1:
            mc_owners_list_str += m + "|"
            discord_owners_list_str += shop_info["owners_discord_list"][i] + "|"
        else:
            mc_owners_list_str += m
            discord_owners_list_str += shop_info["owners_discord_list"][i]

    # TODO: 8- Transfer Shop Info into SQL Database
    # If shop already has a database entry, just update the owners list.
    if shop_already_in_database:
        # Try to update the entry with the new columns and shop channel id
        # mc_owners
        # discord_owners

        database.query(f"UPDATE shops SET mc_owners = \"{mc_owners_list_str}\" WHERE shop_id = {shop_info['sql_id']};")
        database.query(f"UPDATE shops SET discord_owners = \"{discord_owners_list_str}\" WHERE shop_id = {shop_info['sql_id']};")

    # Otherwise insert into table as normal.
    else:
        # Try to insert data into SQL Database
        database.query("INSERT INTO shops (shop_id,shop_name,coords,shop_init,large_shop,service_shop,image,district,shop_status,mc_owners,discord_owners) VALUES (" +
                       f"{shop_info['sql_id']}, \"{shop_info['shop_name']}\", \"{shop_info['shop_coords']}\", {shop_info['initialized']}, {shop_info['large_shop']}, {shop_info['service_shop']}, \"{shop_info['shop_image_url']}\", \"{shop_info['district_number']}\", \"Open\", \"{mc_owners_list_str}\", \"{discord_owners_list_str}\")")

        # Make shop check record to avoid listing in /report
        database.query(f"INSERT INTO shop_checks(shop_id,checked_by_id,shop_status,date_and_time) VALUES({shop_info['sql_id']},{bot.user.id},'✅ OK','{str(datetime.datetime.now()).split('.')[0]}');)")

    # TODO: 9- Create channel in district category
    if new_category is None:
        new_category = await primary_guild.fetch_channel(category_id)

    new_shop_channel = await primary_guild.create_text_channel(f"🆕｜{shop_info['shop_name']}",category=new_category)

    # TODO: 10- Send constructed shop embeds
    # Send first embed and add reactions to it, then send the rest (Trying to keep the interface as close to the same as possible)
    sent_message = await new_shop_channel.send(embeds=[embed_list[0]])
    for react in ['✅','⚠️','❌']:
        await sent_message.add_reaction(emoji=react)

    # We need to split them up like this in order to more easily edit them later on
    for embed in embed_list[1:]:
        await new_shop_channel.send(embeds=[embed])

    # TODO: 11- Update SQL with new Shop Channel ID
    # shop_channel_id
    database.query(f"UPDATE shops SET shop_channel_id = \"{new_shop_channel.id}\" WHERE shop_id = {int(shop_info['sql_id'])};")

    # TODO: 12- Send message in District comments with @ing the district role
    if not shop_already_in_database:
        try:
            await district_comments.send(f"<@&{district_role_mappings[shop_info['district_number']]}> <#{new_shop_channel.id}> has been added to your District.")
        except KeyError:
            logger.log(f"No role mapped for District {shop_info['district_number']}", tag="[WARN] ")
        except AttributeError:
            logger.log(f"Comments channel for District {shop_info['district_number']} was not found.", tag="[ERROR] ")


    # TODO: 13- Return True
    debug(f'{shop_info}')
    return True

async def is_shop_channel(channel):
    # TODO: Does this need to be an async function?
    if type(channel) != discord.TextChannel:
        return False

    if forbidden_name.match(channel.name):
        return False

    if channel.category_id is None:
        return False

    cat_channel = bot.get_channel(channel.category_id)
    if not district_regex.match(cat_channel.name):
        return False

    return True

# TESTING THIS OUT =====================================================================================================================
channel_cache = {}
message_cache = {}
shop_id_cache = {}

# Grab the channel the reaction was in (Cache the API response if it is not a new channel)
async def get_from_channel_cache(channel_id:int):
    """
    Gets a channel from cache OR will fetch and cache an unseen one.

    :param channel_id:
    :return:
    """
    global channel_cache
    str_channel_id = str(channel_id)

    if str_channel_id not in channel_cache:
        channel_cache[str_channel_id] = await primary_guild.fetch_channel(channel_id)
        debug(f"Cached new channel {str_channel_id}")

    return channel_cache[str_channel_id]

async def get_from_message_cache(msg_id:int,channel):
    global message_cache
    msg_id_str = str(msg_id)

    if msg_id_str not in message_cache:
        message_cache[msg_id_str] = await channel.fetch_message(msg_id)

    return message_cache[msg_id_str]

async def delete_channel(channel,reason="Shop closed."):

    global channel_cache
    str_channel_id = str(channel.id)

    if str_channel_id in channel_cache:
        channel_cache.pop(str_channel_id)

    await channel.delete(reason=reason)

async def get_shop_channel_history(shop_channel):
    shop_message_history = []
    async for msg in shop_channel.history(limit=8,oldest_first=True): # Limiting it to 8 messages as there shouldn't be any other than the shop itself
        if msg.author.id == bot.user.id:
            shop_message_history.append(msg)

    if len(shop_message_history) < 4:
        logger.log(f"Cannot find all bot messages in {shop_channel.id}","[ERROR] ")
        return False

    return shop_message_history


def get_shop_id_from_channel_id(channel_id:int):
    channel_id_str = str(channel_id)

    if channel_id_str not in shop_id_cache:
        temp_shop_id = database.query(f"SELECT shop_id FROM shops WHERE shop_channel_id = {channel_id}")[0][0]
        shop_id_cache[channel_id_str] = temp_shop_id
    else:
        temp_shop_id = shop_id_cache[channel_id_str]

    return temp_shop_id

def cache_sql_data():

    """

    OK So for some reason SQL queries are taking the most amount of time. I'm not sure if thats because of my testing enviroment or if it is really taking the long.
    In anycase it looks like it's a problem so I need to at least mitigate it somehow.

    TODO: Thinking at bot launch to grab a large query of shops.

    TODO: ok nevermind because the problem is with shop checks... and cahcing that is too much for this

    :return:
    """


    pass

# END OF TESTING THIS OUT ==============================================================================================================


# New event to print when bot has successfully connected
@bot.event
async def on_ready():
    global primary_guild
    logger.clean_logs(14)
    primary_guild = await bot.fetch_guild(variables['guild_id'])
    logger.log("Bot loaded and connected.", tag="[INFO] ")
    logger.log(f"Logged in as {bot.user}", tag="[INFO] ")

# Event triggered when message sent. Handles Shop Creation.
@bot.event
async def on_message(msg):
    """
    :param msg:
    :return:
    """
    # Ensure message is not the Bot itself
    if msg.author == bot.user:
        debug("Message author is Bot")
        return

    # Ensure channel has a category
    if msg.channel.category_id is None:
        debug("No Category found")
        return



    if msg.channel.category_id == variables['ticket_category_id'] and ticket_regex.match(msg.channel.name):

        # List of process keys, so I didn't have to do this every line
        shop_ticket_process_keys = list(shop_ticket_process.keys())
        sub_ticket_process_keys = list(sub_ticket_process.keys())

        debug("Is in ticket category, matches regex, and is not bot")

        last_bot_message = ""
        expected_response = []
        accepted_response = False
        image_response = False
        next_step = 0

        sub_ticket = False
        sub_ticket_index = 0

        if forbidden_name.match(msg.content):
            debug("Forbidden name found")
            await msg.delete()
            return

        # Get message history
        async for message in msg.channel.history(limit=len(shop_ticket_process_keys)*3):

            # Find latest bot message
            if message.author == bot.user:
                last_bot_message = message.content
                break

        debug(f"last bot message:\n{last_bot_message}")

        if last_bot_message == "":
            logger.log(f"Last bot message not found in ticket {msg.channel.name}","[ERROR] ")
            await msg.delete()
            return

        # Determine expected response
        for k in shop_ticket_process_keys:
            debug(f"Shop ticket process key: {k}")
            if re.compile(shop_ticket_process[k]['message_regex']).fullmatch(last_bot_message):
                expected_response = [shop_ticket_process[k]['response_type'],shop_ticket_process[k]['response_regex']]

                # The index of the next step in the process
                next_step = shop_ticket_process_keys.index(k) + 1

                debug(f"Shop ticket message regex found")
                break

        # Determine expected response (if in sub ticket process)
        if len(expected_response) == 0:
            for k in sub_ticket_process_keys:
                debug(f"Sub ticket process key: {k}")
                if re.compile(sub_ticket_process[k]['message_regex']).fullmatch(last_bot_message):
                    expected_response = [sub_ticket_process[k]['response_type'],sub_ticket_process[k]['response_regex']]
                    sub_ticket = True
                    sub_ticket_index = sub_ticket_process_keys.index(k)
                    debug(f"Sub ticket message regex found")
                    break


        # Non-exception error if no expected response found.
        if len(expected_response) == 0:
            expected_response = ["ERROR"]

        debug(f"Message is digit: {msg.content.isdigit()}")
        debug(f"Message response regex: {expected_response}")
        try:
            debug(f"Message matches regex: {re.compile(expected_response[1], re.IGNORECASE).fullmatch(msg.content)}")
        except IndexError:
            pass
        debug(f"expected response:\n{expected_response}")

        # Look to see if response is acceptable
        if expected_response[0] in ["MESSAGE","IMAGE"]:
            if expected_response[0] == "IMAGE":
                image_response = True

            if expected_response[1] == r"ANY":
                accepted_response = True

            elif expected_response[1] == r"NUMBER" and msg.content.isdigit():
                accepted_response = True

            elif re.compile(expected_response[1], re.IGNORECASE).fullmatch(msg.content):
                accepted_response = True


        else:
            # If not delete the message and do nothing else
            await msg.delete()


        # Check if image is acceptable first
        if image_response:
            accepted_response = False
            for ext in ['.png','.jpg','.jpeg']:
                try:
                    if ext in msg.attachments[0].filename:
                        accepted_response = True
                        break
                except IndexError:
                    debug('No attachments found')


        # If acceptable, proceed to next step
        if accepted_response and next_step < len(shop_ticket_process_keys):

            # Using a list here to allow for more reactions down the line
            add_reactions = []

            # Get next message to send
            if not sub_ticket:
                next_message = shop_ticket_process_keys[next_step]

                # Check if next message is a reaction response
                if shop_ticket_process[shop_ticket_process_keys[next_step]]["response_type"] == "REACTION_YES_OR_NO":
                    add_reactions = ['🇾','🇳']
                elif shop_ticket_process[shop_ticket_process_keys[next_step]]["response_type"] == "REACTION_CHECKMARK":
                    add_reactions = ['✅']
            else:
                next_message = sub_ticket_process[sub_ticket_process_keys[sub_ticket_index]]['main_process_key']

                # Check if next message is a reaction response
                if sub_ticket_process[sub_ticket_process_keys[sub_ticket_index]] == "REACTION_YES_OR_NO":
                    add_reactions = ['🇾','🇳']
                elif sub_ticket_process[sub_ticket_process_keys[sub_ticket_index]] == "REACTION_CHECKMARK":
                    add_reactions = ['✅']


            # Parse and retrieve any data that needs to be filled.
            # TODO: Expand on more maybe?
            next_message = next_message.replace(f'<LAST_MESSAGE>',f'{msg.content}')

            debug(f"NEXT MESSAGE: {next_message}")

            # Send next step message
            sent_message = await msg.channel.send(content=f"{next_message}")
            if len(add_reactions) > 0:
                for react in add_reactions:
                    await sent_message.add_reaction(emoji=react)
                # '✅','🇾','🇳','❌',':white_check_mark:',':regional_indicator_y:',':regional_indicator_n:',':x:'

        # If last step, finish creating the shop
        elif next_step == len(shop_ticket_process_keys):
            debug("Creating new shop - message")

            success = await create_shop_channel(msg.channel)

            # If successfully made shop channel, delete the ticket channel
            if success:

                #await msg.channel.delete()
                await delete_channel(msg.channel,"")

            else:

                logger.log(f"Failed to create shop channel: {msg.channel}","[ERROR] ")

        # If it is not an accepted response, delete the message.
        elif not accepted_response:
            await msg.delete()

# Event triggered when a reaction has been added. Handles Shop Creation and Shop Check
@bot.event
async def on_raw_reaction_add(reaction_data):

    sw = Stopwatch("Check validity section")
    sw3 = Stopwatch("") # sw2 is used inside of other function

    sw.start()

    # Check if the emoji is a valid emoji first
    react_emoji = str(reaction_data.emoji)
    if react_emoji not in ("✅", "⚠️", "❌", "✉️", '✅', '🇾', '🇳', '❌', ':white_check_mark:', ':regional_indicator_y:',
                           ':regional_indicator_n:'):
        debug("Reaction not valid")
        return

    # Check if reaction was in a valid guild and/or channel
    if reaction_data.guild_id != primary_guild.id or reaction_data.channel_id is None:
        debug("Reaction not in guild.")
        return

    # Check if the user reacting exists and/is NOT the bot itself
    reaction_user = await bot.fetch_user(reaction_data.user_id)
    if reaction_user is None:
        debug(f"Reaction User not found")
        return
    if reaction_user == bot.user:
        debug(f"Is Bot reaction")
        return

    channel = await get_from_channel_cache(reaction_data.channel_id)

    if channel.category_id is None or type(channel) != discord.channel.TextChannel:
        debug(f"Reaction not in valid channel.\n{channel}")
        return

    # Get Message, Guild, and Channel
    #guild = await bot.fetch_guild(reaction_data.guild_id)
    #channel = await guild.fetch_channel(reaction_data.channel_id)
    #channel = await bot.fetch_channel(reaction_data.channel_id)

    channel_category = bot.get_channel(channel.category_id)

    debug(f"channel_category: {channel_category}")
    debug(f"Channel type: {type(channel)}")

    #msg = await channel.fetch_message(reaction_data.message_id)
    msg = await get_from_message_cache(reaction_data.message_id,channel)

    sw.stop()

    # SHOP CREATION PROCESS
    # If reaction was in the ticket category
    if channel.category_id == variables['ticket_category_id'] and ticket_regex.match(channel.name) and msg.author == bot.user and reaction_user != bot.user:

        emoji_string = str(reaction_data.emoji)
        debug(f"in watched category & channel. Emoji: {emoji_string}")

        expected_response = ""
        accepted_response = False
        next_step = 0

        sub_ticket = False
        sub_ticket_index = 0

        # List of process keys, so I didn't have to do this every line
        shop_ticket_process_keys = list(shop_ticket_process.keys())
        sub_ticket_process_keys = list(sub_ticket_process.keys())


        # Determine expected response
        for k in shop_ticket_process_keys:
            if re.compile(shop_ticket_process[k]['message_regex']).fullmatch(msg.content):
                expected_response = shop_ticket_process[k]['response_type']

                # The index of the next step in the process
                next_step = shop_ticket_process_keys.index(k) + 1
                debug(f'Next step: {next_step} | {expected_response}')
                break

        # Determine expected response (if in sub ticket process)
        for k in sub_ticket_process_keys:
            if re.compile(sub_ticket_process[k]['message_regex']).fullmatch(msg.content):
                expected_response = sub_ticket_process[k]['response_type']
                sub_ticket = True
                sub_ticket_index = sub_ticket_process_keys.index(k)
                break

        debug(f'Expected response:\n{expected_response}\nSub ticket: {sub_ticket}')

        # Look to see if response is acceptable
        debug(f'Is Expected Response in list:\n{expected_response in ('REACTION_CHECKMARK','REACTION_YES_OR_NO')}')
        if expected_response in ['REACTION_CHECKMARK','REACTION_YES_OR_NO']:
            if expected_response == 'REACTION_CHECKMARK' and emoji_string in ('✅',':white_check_mark:'):
                accepted_response = True
            elif expected_response == 'REACTION_YES_OR_NO' and emoji_string in ('✅','🇾','🇳','❌',':white_check_mark:',':regional_indicator_y:',':regional_indicator_n:',':x:'):
                accepted_response = True


        # If not delete the reaction and do nothing else
        else:
            debug('Clearing reactions')
            await msg.clear_reactions()

        debug(f'Accepted response:\n{accepted_response}')

        # If acceptable, proceed to next step
        if accepted_response and next_step < len(shop_ticket_process_keys):

            # Get if there are any Yes/No special instructions
            if expected_response == 'REACTION_YES_OR_NO': # reaction_data.emoji in ['✅', '🇾', '🇳', '❌']:

                if emoji_string in ('🇳', '❌'):
                    if not sub_ticket:
                        next_message = shop_ticket_process[shop_ticket_process_keys[next_step - 1]]['no_response']
                    else:
                        next_message = sub_ticket_process[sub_ticket_process_keys[sub_ticket_index]]['no_response']

                else:
                    if not sub_ticket:
                        next_message = shop_ticket_process[shop_ticket_process_keys[next_step-1]]['yes_response']

                    else:
                        next_message = sub_ticket_process[sub_ticket_process_keys[sub_ticket_index]]['yes_response']


                # If no special instructions, proceed as normal
                if next_message == 'NORMAL' and not sub_ticket:
                    next_message = shop_ticket_process_keys[next_step]

            # Get if the response is a checkmark
            elif expected_response == 'REACTION_CHECKMARK':
                if not sub_ticket:
                    next_message = shop_ticket_process[shop_ticket_process_keys[next_step - 1]]['yes_response']

                else:
                    next_message = sub_ticket_process[sub_ticket_process_keys[sub_ticket_index]]['yes_response']

            # Otherwise don't worry about it
            else:
                next_message = shop_ticket_process_keys[next_step]


            # Check if next message is a reaction response
            add_reactions = []
            if next_message in shop_ticket_process_keys:

                if shop_ticket_process[next_message]["response_type"] == "REACTION_YES_OR_NO":
                    add_reactions = ('🇾','🇳')
                elif shop_ticket_process[next_message]["response_type"] == "REACTION_CHECKMARK":
                    add_reactions = ('✅')
            else:

                if sub_ticket_process[next_message]["response_type"] == "REACTION_YES_OR_NO":
                    add_reactions = ('🇾','🇳')
                elif sub_ticket_process[next_message]["response_type"] == "REACTION_CHECKMARK":
                    add_reactions = ('✅')


            # Send next step message
            debug(f'Reaction - sending message:\n{next_message}')
            sent_message = await msg.channel.send(content=f"{next_message}")
            if len(add_reactions) > 0:
                for react in add_reactions:
                    await sent_message.add_reaction(emoji=react)


        # If last step, finish creating the shop
        elif next_step == len(shop_ticket_process_keys):
            # TODO: Create function to create the new shop
            debug("Creating new shop - reaction")
            debug("Not implemented yet") # Remove when implemented
            pass

    # SHOP CHECK PROCESS
    # If reaction was in a shop category
    elif district_regex.fullmatch(channel_category.name) and msg.author == bot.user and reaction_user != bot.user:

        sw.start("Get shop channel history")

        shop_message_history = await get_shop_channel_history(channel)

        sw.stop()

        #shop_message_history = []
        #async for msg_2 in channel.history(limit=4,oldest_first=True):
        #    shop_message_history.append(msg_2)

        # MSG INDEX 0 = Main Shop Info
            # FILED 0 = Owners
            # FIELD 1 = Initialized
            # FIELD 2 = Large Shop
            # Field 3 = Service Shop
            # Field 4 = Warnings within 3 months <- adding this *shouldn't* break anything

        # MSG INDEX 1 = Status Legend
        # MSG INDEX 2 = Shop Status & To do
            # FIELD 0 = Status:
            # FIELD 1 = Next Check Due:
            # FIELD 2 = Last checked by:
            # FIELD 3 = Where to do will exist when needed

        # MSG INDEX 3 = Shop check command and where to put message template for sending

        async def log_shop_check_activity(shop_info_message:discord.Message,shop_channel_id:int,checked_by_id:int,status:str) -> int:
            """
            Updates the shop_checks table with this new shop check.
            Returns the number of warnings received within 3 months.

            :param shop_info_message: discord.Message
            :param shop_channel_id: int
            :param checked_by_id: int
            :param status: str
            :return:
            """
            # Players who receive 4 warnings in a 3 month period will have their shop reclaimed automatically
            sw2 = Stopwatch("Log shop check activity")
            sw2.start()

            # temp_shop_id = database.query(f"SELECT shop_id FROM shops WHERE shop_channel_id = {shop_channel_id}")[0][0]
            temp_shop_id = get_shop_id_from_channel_id(shop_channel_id)

            database.query(f"INSERT INTO shop_checks(shop_id,checked_by_id,shop_status,date_and_time) VALUES({temp_shop_id},{checked_by_id},'{status}','{str(datetime.datetime.now()).split('.')[0]}');)")

            # TODO: Maybe look into database sided programming so we can run the calculations in the shops table and not have to this everytime.
            warnings_count = int(database.query(f"SELECT COUNT(date_and_time) FROM shop_checks WHERE shop_id = {temp_shop_id} AND shop_status = '⚠️ Warning' AND date_and_time >= (SELECT MAX(date_and_time) FROM shop_checks WHERE shop_id = {temp_shop_id} AND shop_status = '⚠️ Warning') - INTERVAL 3 MONTH;")[0][0])

            if warnings_count > 0:
                new_embed_two = shop_info_message.embeds[0]

                warnings_count_text = f"{warnings_count}"
                if warnings_count >= 4:
                    warnings_count_text = f"{warnings_count} ⚠️"

                if len(new_embed_two.fields) < 5:
                    new_embed_two.add_field(name="Warnings in the last 3 months:", value=warnings_count_text, inline=False)
                else:
                    new_embed_two.set_field_at(4,name="Warnings in the last 3 months:", value=warnings_count_text, inline=False)

                await shop_info_message.edit(embeds=[new_embed_two])

            sw2.stop()

            return warnings_count

        sw.start("Processing actual check")

        # IF CHECKMARK
        if react_emoji == "✅":

            new_embed = shop_message_history[2].embeds[0]

            new_embed.set_field_at(0,name="Status:",value="✅ OK",inline=False)
            new_embed.set_field_at(1, name="Next Check Due:", value=f"<t:{get_next_check_deadline()}:f>", inline=False)
            new_embed.set_field_at(2, name="Last checked by:", value=f"<@{reaction_user.id}> on <t:{get_current_discord_timecode()}:f>", inline=False)

            if len(new_embed.fields) > 3:
                new_embed.remove_field(3)

            await shop_message_history[2].edit(embeds=[new_embed])

            await shop_message_history[2].clear_reactions()

            await log_shop_check_activity(shop_message_history[0],channel.id,reaction_user.id,"✅ OK")


        # IF WARNING
        if react_emoji == "⚠️":

            new_embed = shop_message_history[2].embeds[0]

            if new_embed.fields[0].value == "⚠️ Warning / Owner Contacted":
                new_embed.set_field_at(1, name="Next Check Due:", value=f"<t:{get_next_check_deadline()}:f>", inline=False)
                new_embed.set_field_at(2, name="Last checked by:", value=f"<@{reaction_user.id}> on <t:{get_current_discord_timecode()}:f>", inline=False)

                await shop_message_history[2].edit(embeds=[new_embed])

            else:
                new_embed.set_field_at(0,name="Status:",value="⚠️ Warning",inline=False)
                new_embed.set_field_at(1, name="Next Check Due:", value=f"<t:{get_next_check_deadline()}:f>", inline=False)
                new_embed.set_field_at(2, name="Last checked by:", value=f"<@{reaction_user.id}> on <t:{get_current_discord_timecode()}:f>", inline=False)


                raw_owners_text = shop_message_history[0].embeds[0].fields[0].value
                owners_list = raw_owners_text.split("\n")
                primary_owner_mc = owners_list[0].split(" (")[0]
                primary_owner_discord = owners_list[0].split(" (")[1].replace(")","")

                shop_name = shop_message_history[0].embeds[0].title.split(" (")[0]


                to_do_text = \
                    f"""
- Contact {primary_owner_mc} ({primary_owner_discord}). You may copy/paste the message below.
  - Create a thread in this channel and post your evidence (screenshot of contact) in that thread.
    - React ✉️ to this message to confirm the owner has been contacted.
                    """

                if len(new_embed.fields) > 3:
                    new_embed.remove_field(3)

                new_embed.add_field(name="To do:",value=to_do_text)

                message_to_send_text = \
                    f"""
    ```Hi {primary_owner_mc}! It appears your shop, {shop_name}, has been inactive for 2 weeks. We require shop owners to be active to reduce the number of empty or neglected shops in our marketplace. For a shop to be considered inactive, the following must be true:
    
    • The owner has not interacted with items in any of the chests in the shop for 4 weeks.
    • The shop has not been added to a marketplace directory within 4 weeks of being built.
    
    And ONE of the following: 
    
    • There have been unclaimed diamonds in the shop for 4 weeks.
    OR
    • There has been no stock, or not enough stock to fulfill the quantity for the price that was set, for 4 weeks.
    
    The purpose of this message is to kindly remind you to restock your shop and/or pick up your unclaimed payments! If you do not do so within 2 weeks **your shop will be reclaimed and put up for auction.**`
    
    Please message me when you do so. If you have any questions, feel free to ask! Thanks!```
                    """


                message_to_send_embed = discord.Embed(color=10181046,title=f"Owner Contact Message - {primary_owner_discord}",description=message_to_send_text)


                await shop_message_history[2].edit(embeds=[new_embed,message_to_send_embed])
                await shop_message_history[2].add_reaction("✉️")

            await log_shop_check_activity(shop_message_history[0], channel.id, reaction_user.id, "⚠️ Warning")

        # IF RED X
        if react_emoji == "❌":
            to_do_text = \
                """
*This shop will not close until all steps are completed!*

- Message the shop owner. You may copy and paste the message below. React 1️⃣ when complete.
  - Send a screenshot of your communication with the owner in the district comments channel. React 2️⃣ when complete.
    - Collect all materials, chests, armor stands, heads, signs, and banners from the shop. Store the items in the Staff HQ at 332, 64 on the nether roof. React 3️⃣ when complete.
      - Remove the shop in the GUI Marketplace directory & `@Shop Check Admin` to notify them. React 4️⃣ when this step is complete. ```/guimd moderate review```
"""
            await shop_message_history[2].clear_reactions()

            new_embed = shop_message_history[2].embeds[0]

            new_embed.set_field_at(0,name="Status:",value="❌ Reclaim",inline=False)
            new_embed.set_field_at(1, name="Next Check Due:", value=f"<t:{get_next_check_deadline()}:f>", inline=False)
            new_embed.set_field_at(2, name="Last checked by:", value=f"<@{reaction_user.id}> on <t:{get_current_discord_timecode()}:f>", inline=False)

            try:
                new_embed.set_field_at(3,name="To do:", value=to_do_text)
                debug("Set field")
            except IndexError:
                new_embed.add_field(name="To do:", value=to_do_text)
                debug("Add field")

            await shop_message_history[2].edit(embeds=[new_embed])

            for r in ("1️⃣","2️⃣","3️⃣","4️⃣"):
                await shop_message_history[2].add_reaction(r)

            await log_shop_check_activity(shop_message_history[0], channel.id, reaction_user.id, "❌ Reclaim")

            # TODO: Add in message template that can be sent to the shop owner


        # IF ENVELOPE EMOJI
        if react_emoji == "✉️":

            new_embed = shop_message_history[2].embeds[0]

            if new_embed.fields[0].value == "⚠️ Warning":

                new_embed.set_field_at(0,name="Status:",value="⚠️ Warning / Owner Contacted",inline=False)

                if len(new_embed.fields) > 3:
                    new_embed.remove_field(3)

            await shop_message_history[2].edit(embeds=[new_embed])

            await msg.clear_reaction(react_emoji)

        try:
            await msg.remove_reaction(react_emoji,reaction_user)
            sw.stop()
        except:
            pass
            sw.stop()

# TODO: COMMANDS TO BE CREATED
"""
DONE !mb create : Creates a shop ticket. Respond to the prompts in the ticket to create a shop.

!mb pop : Repopulates a shop channel in the event a shop channel is made and doesn't populate, or if the bot breaks before the embeds post. Only @Shop Check Admin should be able to use this command. This command may only be used in a shop channel.

PENDING !mb closeshop : Closes the shop. Takes a transcript of the channel and deletes the channel. Should only be used by @Shop Check Admin and only if the shop has been demolished, auctioned, or otherwise closed. This command should only be able to used in a shop channel.

DONE !mb change shopname "<old shop name>" "<new shop name>" : Changes the name of a shop and repopulates embeds for the shop channel. Usable only by @Staff

DONE !mb change coords "<shop name>" "<x y z>" : Changes the coords of a shop and repopulates embeds for the shop channel. Usable only by @Staff

DONE !mb change largeshop "<shop name>" <True/False> : Changes the large shop tag to either True or False, depending on the option entered. Usable only by @Staff

DONE !mb change serviceshop "<shop name>" <True/False> : Changes the service shop tag to either True or False, depending on the option entered. True and False are case-sensitive!! Usable only by @Staff

DONE RENAMED !mb change district "<shop name>" <district#> : Changes the district number the shop is assigned to. Moves the shop channel to the corresponding district category and mentions that district's role. Usable only by @Staff

DONE !mb update owner1 "<shop name>" "<new name>" "<new owner discord ID>" : Changes the 1st owner's name and Discord ID (DiscordID#0000 format) for the shop entered as "shop name". This command may also be used to update the 2nd and 3rd owner names by substituting owner2 and owner3 for "owner1" in the command. Usable only by @Staff

DONE RENAMED !mb newimage "<shop name>" : Changes the image for the shop named in "shop name". This command may only be used in a district comments channel! Usable only by @Staff

IGNORE !mb closeticket <ticket#> : Closes the ticket with the ticket number entered and sends a transcript to #shop-ticket-logs. Usable only by @Shop Check Admin.

DONE !mb search <search term> : allows you to search for shops based on various attributes such as the shop's name, owner names, and owner Discord IDs

DONE !mb claim

DONE !mb report : admin command to grab a report on open shops that have not been checked the current week.
"""

# !mb create
@bot.slash_command(guild_ids=[variables['guild_id']],description="Initiates a shop creation ticket.")
@discord.ext.commands.has_role(variables['shop_staff_id'])
async def create(ctx):

    try:
        ticket_category = None
        for c in ctx.guild.categories:
            if c.id == variables['ticket_category_id']:
                ticket_category = c

        if ticket_category is None:
            logger.log("Category not found.","[ERROR] ")

            raise discord.NotFound

        else:
            new_ticket = await ticket_category.create_text_channel(f"ticket-{get_next_id()}-{ctx.author.name}")

            await new_ticket.send(content=f"{list(shop_ticket_process.keys())[0].replace('<USER>',f'<@{ctx.author.id}>')}")

            await ctx.respond("Ticket created ",ephemeral=True)

    except Exception as e:
        logger.log(f"{e}","[ERROR] ")
        await ctx.respond("Error creating ticket...\nPlease contact Admins.", ephemeral=True)

# !mb pop
# @bot.slash_command(guild_ids=[variables['guild_id']],description="Repopulates the desired shop.")
# @discord.ext.commands.has_role(variables['shop_staff_id'])
async def pop(ctx, channel:discord.Option(discord.TextChannel,description="Shop Channel to close")):
    # TODO: Finish

    # So basically grab data from SQL and edit messages with new? shop embeds. Just going to copy and paste my code from import_from_sql

    result = database.query(f"SELECT * FROM shops WHERE shop_channel_id = {channel.id}")
    #   0    1                2     3       4            5               6            7               8            9               10         11          12            13               14        15           16            17            18             19              20
    #[( id#, shop channel id, name, coords, owner1 name, owner1 discord, owner2 name, owner2 discord, owner3 name, owner3 discord, shop init, large shop, service shop, image (varchar), district, district id, scmessage id, scstatmsg id, ocembedmsg id, reclaim msg id, shop status (Open or Closed) )]

    if len(result) <= 0 and not forbidden_name.fullmatch(channel.name):
        await ctx.respond("Not a valid Shop.",ephemeral=True)

    # Reconstruct Shop info to feed into construct_shop_embeds
    s = result[0]
    shop_info = \
        {
            "shop_name": s[2],
            "shop_coords": s[3],
            "owners_mc_list": s[21],
            "owners_discord_list": s[22]
        }

    # Reconstruct shop embeds
    embeds = construct_shop_embeds(shop_embeds_template,shop_info)

    # Edit messages OR Send messages if not enough exist.
    # Delete excess BOT messages

# !mb help
@bot.slash_command(guild_ids=[variables['guild_id']],description="Displays a list of commands.")
@discord.ext.commands.has_role(variables['shop_staff_id'])
async def help(ctx):
    # TODO: Finish
    pass

# !mb claim
@bot.slash_command(guild_ids=[variables['guild_id']],description="Claims a shop for you.")
@discord.ext.commands.has_role(variables['shop_staff_id'])
async def claim(ctx,channel: discord.Option(discord.TextChannel, description="")):
    debug(f"{ctx.author} trying to claim {channel}")

    if not await is_shop_channel(channel):
        await ctx.respond("Invalid Channel", ephemeral=True)
        return

    try:
        new_name = channel.name.replace(f"{channel.name[0]}",emoji_dict[f"{ctx.author.id}"])
    except KeyError:
        logger.log(f"Emoji for {ctx.author.id} was not found.","[ERROR] ")
        await ctx.respond("Couldn't find emoji.")

    await channel.edit(name=new_name)
    await ctx.respond(f"Claimed <#{channel.id}>")

# !mb closeshop
@bot.slash_command(guild_ids=[variables['guild_id']],description="Closes a shop that has been marked for reclaim. Shop Admins only.")
@discord.ext.commands.has_role(variables['shop_admin_id'])
async def close_shop(ctx):
    # TODO: Finish

    channel = ctx.channel

    if not await is_shop_channel(channel):
        await ctx.respond("Invalid Channel", ephemeral=True)
        return

    shop_message_history = await get_shop_channel_history(channel)

    if shop_message_history is False:
        await ctx.respond("Can't find messages", ephemeral=True)
        return

    # MSG INDEX 0 = Main Shop Info
        # FILED 0 = Owners
        # FIELD 1 = Initialized
        # FIELD 2 = Large Shop
        # Field 3 = Service Shop
        # Field 4 = Warnings within 3 months <- adding this *shouldn't* break anything

    # MSG INDEX 1 = Status Legend
    # MSG INDEX 2 = Shop Status & To do
        # FIELD 0 = Status:
        # FIELD 1 = Next Check Due:
        # FIELD 2 = Last checked by:
        # FIELD 3 = Where to do will exist when needed

    # MSG INDEX 3 = Shop check command and where to put message template for sending

    new_embed = shop_message_history[2].embeds[0]

    if new_embed.fields[0].value == "❌ Reclaim":
        debug("Closing shop")
        await ctx.respond(f"Closing <#{channel.id}>", ephemeral=True)

        # TODO: Find a way to include what was in the threads in transcript
        # TODO: Might need to experiment with using the raw_export function and doing the message gathering myself.
        transcript = await chat_exporter.export(channel,bot=bot)

        transcript_file = discord.File(
            io.BytesIO(transcript.encode()),
            filename=f"transcript-{ctx.channel.name}.html",
        )

        transcript_channel = await get_from_channel_cache(variables["transcripts_channel_id"])
        await transcript_channel.send(file=transcript_file)

        #await bot.get_channel(variables["transcripts_channel_id"]).send(file=transcript_file)

        database.query(f"UPDATE shops SET shop_status = \"Closed\" WHERE shop_channel_id = \"{channel.id}\";")

        #await channel.delete(reason="Shop closed.")

        await delete_channel(channel)

    else:
        await ctx.respond(f"Shop not marked for Reclaim.", ephemeral=True)

# New command to update a shop's image
@bot.slash_command(guild_ids=[variables['guild_id']],description="Updates an image for a shop. Note: This can take a minute.")
@discord.ext.commands.has_role(variables['shop_staff_id'])
async def update_image(ctx, channel:discord.Option(discord.TextChannel,description="Channel to update image") ,image: discord.Option(discord.Attachment,description="Image update to")):
    debug("Updating image")

    # TODO: Check to make sure this is an image filetype

    if not await is_shop_channel(channel):
        await ctx.respond("Invalid Channel", ephemeral=True)
        return

    await ctx.respond(f"Updating <#{channel.id}>")
    url = await store_image(primary_guild,image)

    shop_message_history = await get_shop_channel_history(channel)

    if shop_message_history is False:
        await ctx.respond("Can't find messages", ephemeral=True)
        return

    # MSG INDEX 0 = Main Shop Info
    # FILED 0 = Owners
    # FIELD 1 = Initialized
    # FIELD 2 = Large Shop
    # Field 3 = Service Shop
    # Field 4 = Warnings within 3 months <- adding this *shouldn't* break anything

    # MSG INDEX 1 = Status Legend
    # MSG INDEX 2 = Shop Status & To do
    # FIELD 0 = Status:
    # FIELD 1 = Next Check Due:
    # FIELD 2 = Last checked by:
    # FIELD 3 = Where to do will exist when needed

    # MSG INDEX 3 = Shop check command and where to put message template for sending

    new_embed = shop_message_history[0].embeds[0]

    new_embed.set_image(url=url)

    await shop_message_history[0].edit(embeds=[new_embed])

# New command to update information about a shop
# !mb change shopname, coords, largeshop, serviceshop
@bot.slash_command(guild_ids=[variables['guild_id']],description="Updates information about a shop.")
@discord.ext.commands.has_role(variables['shop_staff_id'])
async def update_shop(ctx, channel: discord.Option(discord.TextChannel,description="Shop's channel"),
                      shop_name: discord.Option(str,description="Name to change to",required=False,default=None),
                      coords: discord.Option(str,description="Coords to change to",required=False,default=None),
                      large_shop: discord.Option(bool,description="Is large shop?",required=False,default=None),
                      service_shop: discord.Option(bool,description="Is service shop?",required=False,default=None)):

    # MSG INDEX 0 = Main Shop Info
    # FILED 0 = Owners
    # FIELD 1 = Initialized
    # FIELD 2 = Large Shop
    # Field 3 = Service Shop
    # Field 4 = Warnings within 3 months <- adding this *shouldn't* break anything

    # MSG INDEX 1 = Status Legend
    # MSG INDEX 2 = Shop Status & To do
    # FIELD 0 = Status:
    # FIELD 1 = Next Check Due:
    # FIELD 2 = Last checked by:
    # FIELD 3 = Where to do will exist when needed

    # MSG INDEX 3 = Shop check command and where to put message template for sending

    # Make sure it's actually in a shop channel.
    if not await is_shop_channel(channel):
        await ctx.respond("Invalid Channel",ephemeral=True)
        return


    await ctx.respond("Updating shop info...")

    shop_message_history = await get_shop_channel_history(channel)

    if shop_message_history is False:
        await ctx.respond("Can't find messages", ephemeral=True)
        return

    # Change shop name if entered
    if shop_name is not None:
        old_embed = shop_message_history[0].embeds[0]

        # <shop_name> (<shop_coords>)
        cur_shop_name = old_embed.title.split(' (')[0]
        sanitized_name = SanitizeString(shop_name,bannedCharacters=['$', '&', '{', '}', '\\', '/', '[', ']', '(', ')', '|', '<','>'])

        old_embed.title = old_embed.title.replace(cur_shop_name, shop_name)

        database.query(f"UPDATE shops SET shop_name = \"{shop_name}\" WHERE shop_channel_id = \"{channel.id}\"")

        await shop_message_history[0].edit(embeds=[old_embed])
        await channel.edit(name=f"{channel.name[:2]}{sanitized_name}")

        debug(f"Changed Shop Name from \"{cur_shop_name}\" to \"{shop_name}\".")

    # Change shop coords if entered
    if coords is not None:
        old_embed = shop_message_history[0].embeds[0]

        # <shop_name> (<shop_coords>)
        cur_shop_coords = old_embed.title.split(' (')[1].replace(')','')
        sanitized_coords = SanitizeString(coords,bannedCharacters=['$', '&', '{', '}', '\\', '/', '[', ']', '(', ')', '|', '<', '>' ,','])

        old_embed.title = old_embed.title.replace(cur_shop_coords, sanitized_coords)

        database.query(f"UPDATE shops SET coords = \"{sanitized_coords}\" WHERE shop_channel_id = \"{channel.id}\"")

        await shop_message_history[0].edit(embeds=[old_embed])
        debug(f"Changed Shop Coords from \"{cur_shop_coords}\" to \"{sanitized_coords}\".")

    # Large shop status if entered
    if large_shop is not None:
        old_embed = shop_message_history[0].embeds[0]

        old_embed.set_field_at(2,name="Large Shop:",value=f"{large_shop}")

        database.query(f"UPDATE shops SET large_shop = {int(large_shop)} WHERE shop_channel_id = \"{channel.id}\"")

        await shop_message_history[0].edit(embeds=[old_embed])
        debug(f"Changed Large Shop to {large_shop}.")

    # Change service shop status if entered
    if service_shop is not None:
        # Updates the service shop in the shop info embed
        old_embed = shop_message_history[0].embeds[0]

        old_embed.set_field_at(2,name="Service Shop:",value=f"{service_shop}")

        database.query(f"UPDATE shops SET large_shop = {int(service_shop)} WHERE shop_channel_id = \"{channel.id}\"")

        await shop_message_history[0].edit(embeds=[old_embed])

        # Updates the shop check command embed
        new_embed = update_shop_check_command_embed(shop_message_history[3].embeds[0], channel.id, service_shop)

        await shop_message_history[3].edit(embeds=[new_embed])

        debug(f"Changed Service Shop to {service_shop}.")

# !mb change district
@bot.slash_command(guild_ids=[variables['guild_id']],description="Moves a shop to a different District.")
@discord.ext.commands.has_role(variables['shop_admin_id'])
async def move_shop(ctx, channel: discord.Option(discord.TextChannel,description="Shop's channel"), district_number: discord.Option(int, description="District Number")):
    if not await is_shop_channel(channel):
        await ctx.respond("Not a valid Channel.",ephemeral=True)
        return

    await ctx.respond(f"Attempting to move <#{channel.id}> to District {district_number}.")

    # Get all category channels
    channels = await primary_guild.fetch_channels()

    for channel_cat in channels:
        if type(channel_cat) != discord.CategoryChannel:
            continue

        # Check name
        # Check get_district_number does not return None
        # Check to make sure the found number matches the one given
        if get_district_number(channel_cat.name) == district_number:
            # If it does, move shop there and update database
            database.query(f"UPDATE shops SET district = {district_number} WHERE shop_channel_id = \"{channel.id}\"")
            await channel.move(end=True,category=channel_cat,reason=f"Requested by <@{ctx.author.id}>")
            await ctx.respond(f"Moved <#{channel.id}> to District {district_number}.")

            # Notify shop
            district_comments = None

            for channel_two in channels:
                if channel_two.name == f"🗒-district-{district_number}-comments":
                    district_comments = channel_two

            try:
                await district_comments.send(
                    f"<@&{district_role_mappings[f'{district_number}']}> <#{channel.id}> has been re-assigned to your District.")
            except KeyError:
                logger.log(f"No role mapped for District {f'{district_number}'}", tag="[WARN] ")
            except AttributeError:
                logger.log(f"Comments channel for District {f'{district_number}'} was not found.",
                           tag="[ERROR] ")

            return

    # If none found after loop finishes then respond saying as much
    await ctx.respond("Unable to find District.")

# !mb update owner
@bot.slash_command(guild_ids=[variables['guild_id']],description="Updates the owners of a shop.")
@discord.ext.commands.has_role(variables['shop_staff_id'])
async def update_owner(ctx, shop: discord.Option(discord.TextChannel,description="Shop's channel",required=True),
                       owner_number: discord.Option(int,description="Owner Number. (1, 2, 3, 4, 5.. 20",required=True),
                       mc_name: discord.Option(str,description="Minecraft Username. Leave blank to remove owner.",default="",required=False),
                       discord_name: discord.Option(str,description="Discord name OR ID",default="",required=False)):

    # Checks if shop actually exists
    #if len(database.query(f"SELECT shop_name FROM shops WHERE shop_channel_id = \"{shop.id}\"")) == 0:
    #    await ctx.respond("Invalid shop.",ephemeral=True)
    #    return

    # TODO: Combine these queries so we can speed this section up
    #mc_owners = database.query(f"SELECT mc_owners FROM shops WHERE shop_channel_id = \"{shop.id}\"")[0][0]
    #discord_owners = database.query(f"SELECT discord_owners FROM shops WHERE shop_channel_id = \"{shop.id}\"")[0][0]
    #is_service_shop = database.query(f"SELECT service_shop FROM shops WHERE shop_channel_id = \"{shop.id}\"")[0][0]

    results = database.query(f"SELECT mc_owners, discord_owners, service_shop FROM shops WHERE shop_channel_id = \"{shop.id}\"")
    if len(results) == 0:
        await ctx.respond("Invalid shop.", ephemeral=True)
        return

    mc_owners = results[0][0]
    discord_owners = results[0][1]
    is_service_shop = results[0][2]

    mc_owners = mc_owners.split('|')
    if "" in mc_owners:
        mc_owners.remove("")

    discord_owners = discord_owners.split('|')
    if "" in discord_owners:
        discord_owners.remove("")

    # Prevents removal of only owner
    if owner_number <= 1 and len(mc_owners) == 1:
        await ctx.respond("Shops must have at least 1 owner.",ephemeral=True)
        return

    # Transmutes the owner number into the correct real index of the owners (1 is 0, 2 is 1, and so on)
    if owner_number > len(mc_owners) < 20:
        owner_number = len(mc_owners)
    elif owner_number > len(mc_owners) >= 20:
        owner_number = 19
    elif owner_number <= 1:
        owner_number = 0
    else:
        owner_number -= 1

    #if owner_number <= 1:
    #    owner_number = 0
    #elif owner_number > 20:
    #    owner_number = 19
    #elif owner_number > len(mc_owners):
    #    owner_number = len(mc_owners) - 1
    #else:
    #    owner_number -= 1

    # Basically checks to see if we're adding, removing, or just updating using some small checks.
    if owner_number < len(mc_owners) or (mc_name == "" and owner_number < len(mc_owners)): # I know this looks redundant, but it's needed trust me bro
        mc_owners.pop(owner_number)
        discord_owners.pop(owner_number)
    elif mc_name == "" and owner_number >= len(mc_owners):
        await ctx.respond("There isn't an owner to remove there.",ephemeral=True)
        return

    if mc_name != "":
        mc_owners.insert(owner_number, mc_name)
        discord_owners.insert(owner_number, discord_name)

    await ctx.respond(f"Updating owner #{owner_number + 1} for <#{shop.id}>...", ephemeral=True)

    shop_message_history = await get_shop_channel_history(shop)

    if shop_message_history is False:
        await ctx.respond("Can't find messages", ephemeral=True)
        return

    # MSG INDEX 0 = Main Shop Info
    # FILED 0 = Owners
    # FIELD 1 = Initialized
    # FIELD 2 = Large Shop
    # Field 3 = Service Shop
    # Field 4 = Warnings within 3 months <- adding this *shouldn't* break anything

    # MSG INDEX 1 = Status Legend
    # MSG INDEX 2 = Shop Status & To do
    # FIELD 0 = Status:
    # FIELD 1 = Next Check Due:
    # FIELD 2 = Last checked by:
    # FIELD 3 = Where to do will exist when needed

    # MSG INDEX 3 = Shop check command and where to put message template for sending

    # "test (`test`)"
    owners_text = ""
    database_mc_owner_text = ""
    database_discord_owner_text = ""
    for i,mc_owner in enumerate(mc_owners):
        owners_text += f"{mc_owner} (`{discord_owners[i]}`)"
        database_mc_owner_text += f"{mc_owner}"
        database_discord_owner_text += f"{discord_owners[i]}"
        if (i < len(mc_owners)-1):
            owners_text += "\n"
            database_mc_owner_text += "|"
            database_discord_owner_text += "|"

    logger.log(f"Updating {shop.name}'s owner #{owner_number} to '{mc_name} (`{discord_name}`')",tag="[INFO] ")

    database.query(f"UPDATE shops SET mc_owners = \"{database_mc_owner_text}\" WHERE shop_channel_id = {shop.id};")
    database.query(f"UPDATE shops SET discord_owners = \"{database_discord_owner_text}\" WHERE shop_channel_id = {shop.id};")

    old_embed = shop_message_history[0].embeds[0]
    old_embed.set_field_at(0,name="Owners:",value=owners_text,inline=False)

    await shop_message_history[0].edit(embeds=[old_embed])

    old_embed = update_shop_check_command_embed(shop_message_history[3].embeds[0], shop_channel_id=shop.id, is_service_shop=bool(int(is_service_shop)))
    await shop_message_history[3].edit(embeds=[old_embed])

# !mb report
@bot.slash_command(guild_ids=[variables['guild_id']],description="Generates a report that shows shops that have not been checked this week.")
@discord.ext.commands.has_role(variables['shop_admin_id'])
async def report(ctx):
    # TODO: Finish

    await ctx.respond("Generating, please wait...")

    # Grab all currently open shops
    #result = database.query("SELECT shop_id, shop_channel_id, district FROM shops WHERE shop_status = \"Open\" ORDER BY district ASC;")

    # TODO: Combine these ^twoV in one using join and redo following code to match.

    # Grab latest shop checks
    #result_two = database.query("SELECT shop_id, MAX(date_and_time) FROM shop_checks GROUP BY shop_id ORDER BY date_and_time DESC;")


    result = database.query(f"SELECT sc.shop_id, sh.district, MAX(sc.date_and_time), sh.shop_channel_id FROM shop_checks sc INNER JOIN shops sh ON sc.shop_id=sh.shop_id WHERE sh.shop_status = \"Open\" GROUP BY sc.shop_id ORDER BY sh.district ASC;")


    # 0        1         2         3
    # shop_id, district, datetime, shop_channel_id
    # [(64, 10, datetime.datetime(2022, 4, 30, 15, 18), 941345257302413332)]

    current_datetime = datetime.datetime.now()

    embed_list = []
    current_embed = None
    current_district = None

    for shop in result:
        late = False
        missing = False

        # Check to see if we are still going through the same district
        if current_district != shop[1]:

            current_district = shop[1]

            if current_embed is not None:
                embed_list.append(current_embed)

            current_embed = discord.Embed(title=f"District {current_district} Report", color=0x00ff00)

        # Check to make sure all Embeds are within discord's limits.
        # Max embeds in a message is 10, max fields is 25, but there is a max of 6000 characters accross ALL embeds in a single message.
        if len(current_embed.fields) >= 20:
            embed_list.append(current_embed)
            current_embed = discord.Embed(title=f"District {current_district} Report cont.", color=0x00ff00)

        if len(embed_list) >= 5:
            await ctx.respond(embeds=embed_list)
            embed_list = []

        # Get the last check for the current shop
        try:
            # last_check = database.query(f"SELECT date_and_time FROM shop_checks WHERE shop_id = {shop[0]} ORDER BY date_and_time DESC LIMIT 1;")[0][0]
            last_check = shop[2]
        except IndexError:
            last_check = None
            late = True
            missing = True


        if not missing:
            time_difference = current_datetime - last_check

            if time_difference.days >= 7:
                late = True

        if late:
            if missing:
                late_check_string = f"⚠️ Last Check: NEVER CHECKED"
            else:
                late_check_string = f"⚠️ Last Check: <t:{int(last_check.timestamp())}>"

            current_embed.add_field(name=f"<#{shop[3]}>",value=late_check_string,inline=False)

    if len(embed_list) > 0:
        await ctx.respond(embeds=embed_list)

# !mb search
@bot.slash_command(guild_ids=[variables['guild_id']],description="Searches through the database to look for a keyword.")
@discord.ext.commands.has_role(variables['shop_staff_id'])
async def search(ctx, search_term: discord.Option(str,description="Shop Name, Owner, or a Keyword. Case sensitive.",required=True)):
    # TODO: Finish
    results = database.query(
        f"SELECT shop_channel_id FROM shops WHERE (shop_name LIKE '%{search_term}%' OR mc_owners LIKE '%{search_term}%' OR discord_owners LIKE '%{search_term}%') AND shop_status = 'Open';")

    if len(results) == 0:
        await ctx.respond("Nothing found.", ephemeral=True)
        return

    message_to_send = "**Results:**\n"

    for r in results:
        message_to_send += f"<#{r[0]}>\n"

    await ctx.respond(message_to_send)


# ========================================================================================[DEV COMMANDS]============================================================================================

# New command to load and create missing shops from SQL database
@bot.slash_command(guild_ids=[variables['guild_id']],description="DO NOT USE Reads all data from the SQL Database and Imports it.")
@discord.ext.commands.has_role(variables['shop_admin_id'])
async def import_from_sql(ctx):
    """
    Reads all data from the SQL Database and creates all shops in the database.
    Basically here to transfer from old marketplace bot to this one.
    :param ctx:
    :return:
    """
    # TODO: Finish
    await ctx.respond("Importing from SQL Database... This **WILL** take a while. (Will respond when done)")
    logger.log("Importing from SQL Database... This will take a while.", "[INFO] ")

    result = database.query("SELECT * FROM shops WHERE shop_status = \"Open\" and shop_init = 1;")
    #   0    1                2     3       4            5               6            7               8            9               10         11          12            13               14        15           16            17            18             19              20
    #[( id#, shop channel id, name, coords, owner1 name, owner1 discord, owner2 name, owner2 discord, owner3 name, owner3 discord, shop init, large shop, service shop, image (varchar), district, district id, scmessage id, scstatmsg id, ocembedmsg id, reclaim msg id, shop status (Open or Closed) )]
    shop_infos = []
    for s in result:
        temp_shop_info = {}
        temp_shop_info["shop_name"] = s[2]
        temp_shop_info["shop_coords"] = s[3]
        temp_owners = []
        temp_owners_discord = []

        temp_owners.append(s[4])
        temp_owners_discord.append(s[5])

        if s[6] is not None:
            temp_owners.append(s[6])
            temp_owners_discord.append(s[7])

        if s[8] is not None:
            temp_owners.append(s[8])
            temp_owners_discord.append(s[9])

        temp_shop_info["owners_mc_list"] = temp_owners
        temp_shop_info["owners_discord_list"] = temp_owners_discord

        temp_shop_info["initialized"] = bool(int(s[10]))

        temp_shop_info["large_shop"] = bool(int(s[11]))

        temp_shop_info["service_shop"] = bool(int(s[12]))

        if str(s[13]).startswith("http"):
            temp_shop_info["shop_image_url"] = f"{s[13]}"
        else:
            temp_shop_info["shop_image_url"] = f"http://images.intellectinitiate.com/{s[13]}"

        temp_shop_info["district_number"] = s[14]

        temp_shop_info["sql_id"] = s[0]

        shop_infos.append(temp_shop_info)

    for shop_info in shop_infos:
        debug(shop_info["shop_name"])
        success = await create_shop_channel(None,shop_info,True)
        debug(f"{shop_info['shop_name']} import Success?: {success}")

        # To help prevent getting rate limited
        time.sleep(1)

    # Reformats the timestamp in the SQL Database
    logger.log("Reformatting shop checks...", tag="[INFO] ")
    result = database.query("SELECT * FROM shop_checks;")
    count = 0
    for sc in result:
        try:
            new_datetime = datetime.datetime.strptime(sc[3].strip(), "%m-%d-%Y %I:%M %p")
        except ValueError:
            continue

        database.query(f"UPDATE shop_checks SET date_and_time = \"{str(new_datetime).split('.')[0]}\" WHERE shop_check_id = {sc[0]};")
        count += 1

        debug(count)

    logger.log(f"Reformatted {count} shop check entries.", tag="[INFO] ")


    logger.log("SQL Import & Reformat completed.","[INFO] ")
    await ctx.respond("SQL Import & Reformat completed.\n<@142471642440794112> now delete this command :)")

@bot.slash_command(guild_ids=[variables['guild_id']],description="DO NOT USE Reformats datetimes in shop checks to new format.")
@discord.ext.commands.has_role(variables['shop_admin_id'])
async def reformat_shop_checks_sql(ctx):
    """
    The point of reformatting this is to not have to format the datetime format everytime we want to use it between MySQL and Python.
    Also, it lets us do date calculations in SQL and not in python.

    Should ONLY BE RAN ONCE.

    :param ctx:
    :return:
    """

    await ctx.respond("Reformatting Shop checks SQL... This **WILL** take forever to do.")
    logger.log("Reformatting shop checks...", tag="[INFO] ")
    result = database.query("SELECT * FROM shop_checks;")
    count = 0
    for sc in result:
        try:
            new_datetime = datetime.datetime.strptime(sc[3].strip(), "%m-%d-%Y %I:%M %p")
        except ValueError or AttributeError:
            continue

        database.query(f"UPDATE shop_checks SET date_and_time = \"{str(new_datetime).split('.')[0]}\" WHERE shop_check_id = {sc[0]};")
        count += 1

        debug(count)

    logger.log(f"Reformatted {count} shop check entries.", tag="[INFO] ")
    await ctx.respond("Done.")

# New command to load and create missing shops from SQL database
# @bot.slash_command(guild_ids=[variables['guild_id']],description="DO NOT USE Reformats all entered SQL data")
# @discord.ext.commands.has_role(variables['shop_admin_id'])
async def reformat(ctx):
    """
    Changes SQL Database to new formats. Hopefully will allow this bot to be a drop in replacement.

    :param ctx:
    :return:
    """
    # TODO: Remove, we're not reformatting current discord server
    # TODO: Transform all entries in timestamps to datetime values in the date_and_time column

    await ctx.respond("Reformatting SQL Database... This may take a while.\nDO NOT USE OTHER BOT FUNCTIONS UNTIL THIS IS DONE!")
    logger.log("Reformatting SQL Database... This may take a while.", "[INFO] ")

    debug("Debug mode is True")

    result = database.query("SELECT * FROM shops WHERE shop_init = 1;")
    #   0    1                2     3       4            5               6            7               8            9               10         11          12            13               14        15           16            17            18             19              20
    #[( id#, shop channel id, name, coords, owner1 name, owner1 discord, owner2 name, owner2 discord, owner3 name, owner3 discord, shop init, large shop, service shop, image (varchar), district, district id, scmessage id, scstatmsg id, ocembedmsg id, reclaim msg id, shop status (Open or Closed) )]
    shop_infos = []
    for s in result:
        temp_shop_info = {}

        # Gather all old owner information
        temp_owners = []
        temp_owners_discord = []

        temp_owners.append(s[4])
        temp_owners_discord.append(s[5])

        # Check to make sure owner2 has information
        if s[6].lower() != "none" and len(s[6]) > 0:
            temp_owners.append(s[6])
            temp_owners_discord.append(s[7])

        # Check to make sure owner3 has information
        if s[8].lower() != "none" and len(s[8]) > 0:
            temp_owners.append(s[8])
            temp_owners_discord.append(s[9])

        temp_shop_info["owners_mc_list"] = temp_owners
        temp_shop_info["owners_discord_list"] = temp_owners_discord

        shop_infos.append(temp_shop_info)

        # Create blank owner strings to upload into the SQL Database later
        mc_owners_list_str = ""
        discord_owners_list_str = ""

        # Same blank owner list, but in the format for the actual discord embed
        embed_owners_list_str = ""

        for i, m in enumerate(temp_owners):
            if i < len(temp_owners) - 1:
                mc_owners_list_str += m + "|"
                discord_owners_list_str += temp_owners_discord[i] + "|"

                embed_owners_list_str += f"{m} (`{temp_owners_discord[i]}`)\n"
            else:
                mc_owners_list_str += m
                discord_owners_list_str += temp_owners_discord[i]

                embed_owners_list_str += f"{m} (`{temp_owners_discord[i]}`)"

        # Upload new owner information into the database
        database.query(f"UPDATE shops SET mc_owners = \"{mc_owners_list_str}\" WHERE shop_id = {int(s[0])};")
        database.query(f"UPDATE shops SET discord_owners = \"{discord_owners_list_str}\" WHERE shop_id = {int(s[0])};")

        if debug_mode:
            debug(f"Reformatted: {s[2]}")
            continue

        # Overwrite the existing Owners field with the new format
        shop_channel = await bot.fetch_channel(int(database.query(f"SELECT shop_channel_id FROM shops WHERE shop_id = {s[0]};")[0][0]))

        shop_message_history = []
        async for msg in shop_channel.history(oldest_first=True):
            if msg.author.id == bot.user.id:
                if len(shop_message_history) == 4:
                    await msg.delete()
                else:
                    shop_message_history.append(msg)

        if len(shop_message_history) < 4:
            logger.log(f"Unable to find all 4 embeds for {s[2]} | <#{s[1]}>","[ERROR] ")
            continue

        new_embed = shop_message_history[0].embeds[0]
        new_embed.set_field_at(index=0, name="Owners:", value=embed_owners_list_str, inline=False)

        await shop_message_history[0].edit(embeds=[new_embed])

        # TODO: Implement this fully into here
        update_shop_check_command_embed(shop_message_history[3].embeds[0])

        debug(f"Reformatted: {s[2]}")

    logger.log("Reformatting shop checks...", tag="[INFO] ")
    result = database.query("SELECT * FROM shop_checks;")
    count = 0
    for sc in result:
        try:
            new_datetime = datetime.datetime.strptime(sc[3].strip(), "%m-%d-%Y %I:%M %p")
        except ValueError:
            continue

        database.query(f"UPDATE shop_checks SET date_and_time = \"{str(new_datetime).split('.')[0]}\" WHERE shop_check_id = {sc[0]};")
        count += 1

        debug(count)

    logger.log(f"Reformatted {count} shop check entries.", tag="[INFO] ")

    logger.log("Reformat completed.","[INFO] ")

# @bot.slash_command(guild_ids=[variables['guild_id']],description="test command to delete later")
async def test(ctx):
    await ctx.respond('testing',ephemeral=True)
    res = construct_shop_embeds(shop_embeds_template,
                                {"shop_image_url":"https://upload.wikimedia.org/wikipedia/en/b/b6/Minecraft_2024_cover_art.png",
                                 "shop_name":'my shop',
                                 "shop_coords":'1 1 1',
                                 "owners_mc_list":['FutureCrafter47'],
                                 "owners_discord_list":['envyinggolem47'],
                                 "initialized":True,
                                 "large_shop":False,
                                 "service_shop":False,
                                 "status":"STATUS",
                                 "next_check":"NEXT CHECK",
                                 "last_checked_by":142471642440794112,
                                 "last_checked":'LAST CHECKED'})

    new_list = []
    for r in res:
        new_list.append(r.to_dict())
    saveJsonToFile('test.json',new_list)
    debug('saved')
    time.sleep(1)
    new_list_two = getJsonFromFile('test.json')
    debug('loaded')

    for i,n in enumerate(new_list_two):
        new_list_two[i]=discord.Embed().from_dict(n)

    await ctx.channel.send(embeds=new_list_two)

# ========================================================================================[DEV COMMANDS]============================================================================================

# New command to create a shop, but without going through the process in a channel.
#@bot.slash_command(guild_ids=[variables['guild_id']],description="Create a shop but by just using the command.")
async def cmd_create(ctx,
                     shop_name: discord.Option(str,description="Shop Name"),
                     shop_coords: discord.Option(str,description="Shop Coords Format: X X X"),
                     owners_mc_list: discord.Option(str,description="List of Owners' In Game Usernames. Seperate with |"),
                     owners_discord_list: discord.Option(str,description="List of Owners' Discord Usernames/IDs. Seperate with |"),
                     large_shop: discord.Option(bool,description="Is it a large shop?"),
                     service_shop: discord.Option(bool,description="Is it a service shop?"),
                     shop_image: discord.Option(discord.Attachment,description="Image update to"),
                     district_number: discord.Option(int,description="District Number")):
    # TODO: Finish
    pass

# New command to map roles to districts
@bot.slash_command(guild_ids=[variables['guild_id']],description="Map a role to a district number.")
@discord.ext.commands.has_role(variables['shop_admin_id'])
async def assign_role_to_district(ctx, role: discord.Option(discord.Role, description="Role to assign."),district_number: discord.Option(int, description="District number to assign to.")):
    """
    Assigns a mapping for district to role ID.

    :param ctx:
    :return:
    """

    district_role_mappings[str(district_number)] = role.id
    saveJsonToFile(district_role_mappings_file,district_role_mappings)
    await ctx.respond("Role mapped.",ephemeral=True)
    logger.log(f"Assigned Role ID {role.id} to District {district_number}", tag="[INFO] ")

# Cogs go here (if any)

# Attempts to run the bot
try:
    bot.run(variables['token'])
except discord.errors.LoginFailure:
    input("Invalid Token. (press enter to close) ")