# Python Marketplace Discord Bot, Version: Alpha - 9.9.2026
###### By: EnvyingGolem47 - *( I have no relation to Discord, my opinions are my own and not representative of Discord.)*

Built for Project Nebula.

I'll fill this out better later (trust)

## Installation:

- Download as a zip file
- Set up mysql server and database
- Install python 3.12
- Install dependencies
  - `pip install "superutilities==0.2.5"`
  - `pip install "py-cord==2.7.1"`
  - `pip install "mysql-connector-python==26.7.0"`
- Extract zip file to desired folder
- Run bot.py and follow the first startup instructions




# <u>Code Documentation (to be moved)</u>:

## Shop creation documentation

### <u>Expected response types</u>:
- **"MESSAGE"** - Expects a message response


- **"REACTION_YES_OR_NO"** - Expects a reaction of either Yes or No emojis


- **"REACTION_CHECKMARK"** - Expects a reaction of a :white_check_mark: emoji


- **"NONE"** - Expects nothing


- **"IMAGE"** - Expects Image

### <u>Replacement syntax</u>:
**\<USER>** - replaced with the user that created the ticket - NOTE: Only usable in the first question.

**<LAST_MESSAGE>** - replaced with the last message the user sent

### <u>Keys</u>:
- **"response_type"** is the type of response expected (see above list) ^


- **"message_regex"** (The second item in the list) is the regex that matches the question.


- **"response_regex"** is the regex that the answer is expected to match ( ANY bypasses the check ) ( NUMBER will use .isdigit instead )


- **"yes_response"** (for REACTION_YES_OR_NO & REACTION_CHECKMARK) determines the sub process triggered for a YES ( NORMAL proceeds with main ticket process )


- **"no_response"** (for REACTION_YES_OR_NO) determines the sub process triggered for a NO ( NORMAL proceeds with main ticket process )


- **"stored_variable"** is the variable the response will be stored in

#### Variable naming:

- Should always be lowercase with spaces being replaced with '_'

- Variables that end with "_list" will be automatically stored inside a list in the bot.

### <u>Example</u>:
```json
{
  "Hi, <USER>! Let's create a shop! What is your shop's name?": {
    "response_type": "MESSAGE",
    "message_regex": "Hi, \\S*! Let's create a shop! What is your shop's name\\?",
    "response_regex": "ANY",
    "stored_variable": "shop_name"
    },
  "Great! We will name this shop <LAST_MESSAGE>. Where is this shop located? X Y Z format, please!": {
    "response_type": "MESSAGE",
    "message_regex": "Great! We will name this shop [\\S\\s]*\\. Where is this shop located\\? X Y Z format, please!",
    "response_regex": "-?[0-9]* -?[0-9]* -?[0-9]*",
    "stored_variable": "shop_coords"
    },
  "<LAST_MESSAGE> is a fabulous location! Who owns this shop? Minecraft IGN, please!": {
    "response_type": "MESSAGE",
    "message_regex": "\\S* \\S* \\S* is a fabulous location! Who owns this shop\\? Minecraft IGN, please!",
    "response_regex": "ANY",
    "stored_variable": "owners_mc_list"
    },
    "Has this shop been added to the GUI Marketplace Directory? React :regional_indicator_y: for \"Yes\", or :regional_indicator_n: for \"No\".": {
        "response_type": "REACTION_YES_OR_NO",
        "message_regex": "Has this shop been added to the GUI Marketplace Directory\\? React :regional_indicator_y: for \"Yes\", or :regional_indicator_n: for \"No\"\\.",
        "response_regex": "ANY",
        "yes_response": "NORMAL",
        "no_response": "Oh no! Please contact the owner(s) and ask them to add their shop to a GUI Marketplace Directory! (React with a \u2705 when it has been added)",
        "stored_variable": "initialized"
    },
    "Perfect! Is this a large and/or tall shop? React, please!": {
        "response_type": "REACTION_YES_OR_NO",
        "message_regex": "Perfect! Is this a large and\\/or tall shop\\? React, please!",
        "response_regex": "ANY",
        "yes_response": "NORMAL",
        "no_response": "NORMAL",
        "stored_variable": "large_shop"
    }
}
```

### <u>Sub-ticket Example</u>:
```json
{
  "Oh no! Please contact the owner(s) and ask them to add their shop to a GUI Marketplace Directory! (React with a \u2705 when it has been added)": {
    "response_type": "REACTION_CHECKMARK",
    "message_regex": "Oh no! Please contact the owner\\(s\\) and ask them to add their shop to a GUI Marketplace Directory! \\(React with a \u2705 when it has been added\\)",
    "response_regex": "ANY",
    "yes_response": "Perfect! Is this a large and/or tall shop? React, please!",
    "stored_variable": "initialized"
    }
}
```
