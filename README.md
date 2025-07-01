# Set up the environment
Create the virtual environment, and install the packages in requirements.txt.

# Run the test
python test_bot.py

# Description
The app consists of a simple bot that, when invited to a channel, keeps trace of all the messages for each user/saved messages (save with the reaction 📥). Each message on the channel is considered an inbox message for each user in the channel (except the sender). The statistics are printed in stdout of the application every 5 seconds.
Please create a .env file with the following structure:

### Bot User OAuth Token (starts with xoxb-)
SLACK_BOT_TOKEN=xoxb-..

### App-Level Token (starts with xapp-)
SLACK_APP_TOKEN=xapp-..

Run the app using:
python slack_bot.py.

