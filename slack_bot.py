import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set
from collections import defaultdict
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SlackMessageTracker:
    def __init__(self):
        self.client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
        self.socket_client = SocketModeClient(
            app_token=os.environ.get("SLACK_APP_TOKEN"),
            web_client=self.client
        )
        
        # Data structures to track messages
        self.user_inbox_counts = defaultdict(int)  # user_id -> message_count
        self.user_saved_messages = defaultdict(set)  # user_id -> set of message_ids
        self.user_reminders = defaultdict(list)  # user_id -> list of reminder messages
        self.message_reactions = defaultdict(dict)  # message_id -> {user_id: reaction_type}
        
        # Track users who have interacted with the bot
        self.active_users = set()
        
        # Register event handlers
        self.socket_client.socket_mode_request_listeners.append(self.handle_socket_mode_request)
        
    def start(self):
        """Start the bot"""
        logger.info("Starting Slack Message Tracker Bot...")
        self.socket_client.connect()
        
    def stop(self):
        """Stop the bot"""
        logger.info("Stopping Slack Message Tracker Bot...")
        self.socket_client.disconnect()
        
    def handle_socket_mode_request(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle incoming socket mode requests"""
        try:
            if req.type == "events_api":
                # Acknowledge the request
                response = SocketModeResponse(envelope_id=req.envelope_id)
                client.send_socket_mode_response(response)
                
                # Process the event
                self.process_event(req.payload)
        except Exception as e:
            logger.error(f"Error handling socket mode request: {e}")
            
    def process_event(self, payload: dict):
        """Process different types of Slack events"""
        event = payload.get("event", {})
        event_type = event.get("type")
        
        if event_type == "message":
            self.handle_message_event(event)
        elif event_type == "reaction_added":
            self.handle_reaction_added(event)
        elif event_type == "reaction_removed":
            self.handle_reaction_removed(event)
        elif event_type == "app_mention":
            self.handle_app_mention(event)
            
    def handle_message_event(self, event: dict):
        """Handle new message events"""
        user_id = event.get("user")
        channel_id = event.get("channel")
        message_id = event.get("ts")
        
        if user_id and not event.get("bot_id"):
            # Increment inbox count for all users in the channel
            try:
                # Get channel members
                members = self.get_channel_members(channel_id)
                for member_id in members:
                    if member_id != user_id:  # Don't count sender's own messages
                        self.user_inbox_counts[member_id] += 1
                        self.active_users.add(member_id)
                        
                logger.info(f"Message from {user_id} in {channel_id} - Updated inbox counts for {len(members)-1} users")
                
            except SlackApiError as e:
                logger.error(f"Error getting channel members: {e}")
                
    def handle_reaction_added(self, event: dict):
        """Handle reaction added events (saved for others)"""
        user_id = event.get("user")
        message_id = event.get("item", {}).get("ts")
        reaction = event.get("reaction")
        
        if user_id and message_id:
            # Only save messages with inbox_tray emoji
            if reaction == "inbox_tray":
                self.user_saved_messages[user_id].add(message_id)
                self.message_reactions[message_id][user_id] = reaction
                self.active_users.add(user_id)
                logger.info(f"User {user_id} saved message {message_id} with inbox_tray reaction")
            else:
                logger.info(f"User {user_id} added reaction '{reaction}' to message {message_id} (not saved)")
            
    def handle_reaction_removed(self, event: dict):
        """Handle reaction removed events"""
        user_id = event.get("user")
        message_id = event.get("item", {}).get("ts")
        reaction = event.get("reaction")
        
        if user_id and message_id:
            # Only handle inbox_tray reaction removal
            if reaction == "inbox_tray":
                self.user_saved_messages[user_id].discard(message_id)
                if user_id in self.message_reactions[message_id]:
                    del self.message_reactions[message_id][user_id]
                # Clean up empty message_reactions entry
                if not self.message_reactions[message_id]:
                    del self.message_reactions[message_id]
                logger.info(f"User {user_id} unsaved message {message_id} (removed inbox_tray)")
            else:
                logger.info(f"User {user_id} removed reaction '{reaction}' from message {message_id} (not saved)")
            
    def handle_app_mention(self, event: dict):
        """Handle when the bot is mentioned"""
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        
        if "stats" in text.lower() or "statistics" in text.lower():
            self.send_user_stats(user_id, channel_id)
        elif "help" in text.lower():
            self.send_help_message(channel_id)
            
    def get_channel_members(self, channel_id: str) -> List[str]:
        """Get list of member IDs in a channel"""
        try:
            response = self.client.conversations_members(channel=channel_id)
            return response["members"]
        except SlackApiError as e:
            logger.error(f"Error getting channel members: {e}")
            return []
            
    def send_user_stats(self, user_id: str, channel_id: str):
        """Send statistics for a specific user"""
        inbox_count = self.user_inbox_counts.get(user_id, 0)
        saved_count = len(self.user_saved_messages.get(user_id, set()))
        
        stats_text = f"📊 *Your Statistics:*\n• Inbox messages: {inbox_count}\n• Saved messages: {saved_count}"
        
        try:
            self.client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=stats_text
            )
        except SlackApiError as e:
            logger.error(f"Error sending stats: {e}")
            
    def send_help_message(self, channel_id: str):
        """Send help message"""
        help_text = """
🤖 *Slack Message Tracker Bot Help*

*Commands:*
• `@bot stats` - Show your message statistics
• `@bot help` - Show this help message

*Features:*
• Automatically tracks inbox message counts
• Tracks saved messages for others (only with 📥 inbox_tray reaction)
• Provides statistics on demand

*How to save messages:*
• Add 📥 (inbox_tray) reaction to any message to save it for others
• Other reactions are tracked but not counted as saved messages
        """
        
        try:
            self.client.chat_postMessage(
                channel=channel_id,
                text=help_text
            )
        except SlackApiError as e:
            logger.error(f"Error sending help: {e}")
            
    def print_statistics(self):
        """Print comprehensive statistics to console"""
        print("\n" + "="*60)
        print("📊 SLACK MESSAGE TRACKER STATISTICS")
        print("="*60)
        print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Active users: {len(self.active_users)}")
        print("-"*60)
        
        if not self.active_users:
            print("No active users found.")
            return
            
        # Get user names for better display
        user_names = {}
        for user_id in self.active_users:
            try:
                response = self.client.users_info(user=user_id)
                user_info = response["user"]
                user_names[user_id] = user_info.get("real_name", user_info.get("name", user_id))
            except SlackApiError:
                user_names[user_id] = user_id
                
        # Print individual user statistics
        for user_id in sorted(self.active_users):
            name = user_names[user_id]
            inbox_count = self.user_inbox_counts.get(user_id, 0)
            saved_count = len(self.user_saved_messages.get(user_id, set()))
            
            print(f"👤 {name} ({user_id})")
            print(f"   💾 Inbox messages: {inbox_count}")
            print(f"   📥 Saved messages for others: {saved_count}")
            
            # Show some saved message details
            saved_messages = self.user_saved_messages.get(user_id, set())
            if saved_messages:
                print(f"   📋 Recent saved messages:")
                for msg_id in list(saved_messages)[-3:]:  # Show last 3
                    reactions = self.message_reactions.get(msg_id, {})
                    reaction_str = ", ".join([f"{reaction}" for reaction in reactions.values()])
                    print(f"      • {msg_id} {reaction_str}")
            print()
            
        # Print summary statistics
        total_inbox = sum(self.user_inbox_counts.values())
        total_saved = sum(len(messages) for messages in self.user_saved_messages.values())
        
        print("-"*60)
        print(f"📈 SUMMARY:")
        print(f"   Total inbox messages tracked: {total_inbox}")
        print(f"   Total saved messages for others: {total_saved}")
        print(f"   Average inbox per user: {total_inbox/len(self.active_users):.1f}")
        print(f"   Average saved per user: {total_saved/len(self.active_users):.1f}")
        print("="*60)

def main():
    """Main function to run the bot"""
    # Check for required environment variables
    if not os.environ.get("SLACK_BOT_TOKEN"):
        print("❌ Error: SLACK_BOT_TOKEN environment variable is required")
        return
        
    if not os.environ.get("SLACK_APP_TOKEN"):
        print("❌ Error: SLACK_APP_TOKEN environment variable is required")
        return
        
    # Create and start the bot
    tracker = SlackMessageTracker()
    
    try:
        tracker.start()
        
        # Print statistics every 5 seconds
        import time
        while True:
            time.sleep(5)  # 5 seconds
            tracker.print_statistics()
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping bot...")
        tracker.stop()
        tracker.print_statistics()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        tracker.stop()

if __name__ == "__main__":
    main() 