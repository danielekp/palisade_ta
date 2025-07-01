#!/usr/bin/env python3
"""
Test script for the Slack Message Tracker Bot
This script tests the bot's functionality without requiring actual Slack tokens.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from slack_bot import SlackMessageTracker
from collections import defaultdict

class TestSlackMessageTracker(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock the Slack client
        with patch('slack_bot.WebClient'), patch('slack_bot.SocketModeClient'):
            self.tracker = SlackMessageTracker()
            
    def test_initialization(self):
        """Test that the bot initializes correctly"""
        self.assertIsInstance(self.tracker.user_inbox_counts, defaultdict)
        self.assertIsInstance(self.tracker.user_saved_messages, defaultdict)
        self.assertIsInstance(self.tracker.active_users, set)
        
    def test_handle_message_event(self):
        """Test message event handling"""
        # Mock channel members
        self.tracker.get_channel_members = Mock(return_value=['U123', 'U456', 'U789'])
        
        # Test message event
        event = {
            'user': 'U123',
            'channel': 'C123',
            'ts': '1234567890.123'
        }
        
        self.tracker.handle_message_event(event)
        
        # Check that inbox counts were updated for other users
        self.assertEqual(self.tracker.user_inbox_counts['U456'], 1)
        self.assertEqual(self.tracker.user_inbox_counts['U789'], 1)
        self.assertEqual(self.tracker.user_inbox_counts['U123'], 0)  # Sender shouldn't be counted
        
        # Check that users were added to active users
        self.assertIn('U456', self.tracker.active_users)
        self.assertIn('U789', self.tracker.active_users)
        
    def test_handle_reaction_added_inbox_tray(self):
        """Test inbox_tray reaction added event handling"""
        event = {
            'user': 'U123',
            'item': {'ts': '1234567890.123'},
            'reaction': 'inbox_tray'
        }
        
        self.tracker.handle_reaction_added(event)
        
        # Check that message was saved
        self.assertIn('1234567890.123', self.tracker.user_saved_messages['U123'])
        self.assertEqual(self.tracker.message_reactions['1234567890.123']['U123'], 'inbox_tray')
        self.assertIn('U123', self.tracker.active_users)
        
    def test_handle_reaction_added_other_emoji(self):
        """Test other reaction added event handling (should not save)"""
        event = {
            'user': 'U123',
            'item': {'ts': '1234567890.123'},
            'reaction': '👍'
        }
        
        self.tracker.handle_reaction_added(event)
        
        # Check that message was NOT saved
        self.assertNotIn('1234567890.123', self.tracker.user_saved_messages['U123'])
        self.assertNotIn('1234567890.123', self.tracker.message_reactions)
        self.assertNotIn('U123', self.tracker.active_users)
        
    def test_handle_reaction_removed_inbox_tray(self):
        """Test inbox_tray reaction removed event handling"""
        # First add an inbox_tray reaction
        add_event = {
            'user': 'U123',
            'item': {'ts': '1234567890.123'},
            'reaction': 'inbox_tray'
        }
        self.tracker.handle_reaction_added(add_event)
        
        # Then remove it
        remove_event = {
            'user': 'U123',
            'item': {'ts': '1234567890.123'},
            'reaction': 'inbox_tray'
        }
        self.tracker.handle_reaction_removed(remove_event)
        
        # Check that message was unsaved
        self.assertNotIn('1234567890.123', self.tracker.user_saved_messages['U123'])
        # The message_reactions entry should be completely removed
        self.assertNotIn('1234567890.123', self.tracker.message_reactions)
        
    def test_handle_reaction_removed_other_emoji(self):
        """Test other reaction removed event handling (should not affect saved messages)"""
        # First add an inbox_tray reaction
        add_event = {
            'user': 'U123',
            'item': {'ts': '1234567890.123'},
            'reaction': 'inbox_tray'
        }
        self.tracker.handle_reaction_added(add_event)
        
        # Then remove a different reaction
        remove_event = {
            'user': 'U123',
            'item': {'ts': '1234567890.123'},
            'reaction': '👍'
        }
        self.tracker.handle_reaction_removed(remove_event)
        
        # Check that message is still saved
        self.assertIn('1234567890.123', self.tracker.user_saved_messages['U123'])
        self.assertEqual(self.tracker.message_reactions['1234567890.123']['U123'], 'inbox_tray')
        
    def test_multiple_reactions_same_message(self):
        """Test multiple users reacting to the same message with inbox_tray"""
        # User 1 adds inbox_tray reaction
        event1 = {
            'user': 'U123',
            'item': {'ts': '1234567890.123'},
            'reaction': 'inbox_tray'
        }
        self.tracker.handle_reaction_added(event1)
        
        # User 2 adds different reaction (should not be saved)
        event2 = {
            'user': 'U456',
            'item': {'ts': '1234567890.123'},
            'reaction': '👍'
        }
        self.tracker.handle_reaction_added(event2)
        
        # Check only inbox_tray reaction is saved
        self.assertIn('1234567890.123', self.tracker.user_saved_messages['U123'])
        self.assertNotIn('1234567890.123', self.tracker.user_saved_messages['U456'])
        self.assertEqual(self.tracker.message_reactions['1234567890.123']['U123'], 'inbox_tray')
        self.assertNotIn('U456', self.tracker.message_reactions['1234567890.123'])
        
    def test_statistics_calculation(self):
        """Test statistics calculation"""
        # Add some test data
        self.tracker.user_inbox_counts['U123'] = 10
        self.tracker.user_inbox_counts['U456'] = 15
        self.tracker.user_saved_messages['U123'] = {'msg1', 'msg2'}
        self.tracker.user_saved_messages['U456'] = {'msg3'}
        self.tracker.message_reactions['msg1'] = {'U123': 'inbox_tray'}
        self.tracker.message_reactions['msg2'] = {'U123': 'inbox_tray'}
        self.tracker.message_reactions['msg3'] = {'U456': 'inbox_tray'}
        self.tracker.active_users = {'U123', 'U456'}
        
        # Mock user info
        mock_user_info = {
            'user': {
                'real_name': 'Test User',
                'name': 'testuser'
            }
        }
        
        with patch.object(self.tracker.client, 'users_info', return_value=mock_user_info):
            # Capture print output
            import io
            import sys
            captured_output = io.StringIO()
            sys.stdout = captured_output
            
            self.tracker.print_statistics()
            
            # Restore stdout
            sys.stdout = sys.__stdout__
            output = captured_output.getvalue()
            
            # Check that statistics are included
            self.assertIn('Test User', output)
            self.assertIn('Inbox messages: 10', output)
            self.assertIn('Inbox messages: 15', output)
            self.assertIn('Saved messages for others: 2', output)
            self.assertIn('Saved messages for others: 1', output)
            self.assertIn('Total inbox messages tracked: 25', output)
            self.assertIn('Total saved messages for others: 3', output)
            
    def test_app_mention_handling(self):
        """Test app mention event handling"""
        # Mock the send methods
        self.tracker.send_user_stats = Mock()
        self.tracker.send_help_message = Mock()
        
        # Test stats command
        stats_event = {
            'user': 'U123',
            'channel': 'C123',
            'text': '<@BOT_ID> stats'
        }
        self.tracker.handle_app_mention(stats_event)
        self.tracker.send_user_stats.assert_called_once_with('U123', 'C123')
        
        # Test help command
        help_event = {
            'user': 'U123',
            'channel': 'C123',
            'text': '<@BOT_ID> help'
        }
        self.tracker.handle_app_mention(help_event)
        self.tracker.send_help_message.assert_called_once_with('C123')

def run_tests():
    """Run all tests"""
    print("🧪 Running Slack Message Tracker Bot Tests...")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSlackMessageTracker)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("=" * 50)
    if result.wasSuccessful():
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    run_tests() 