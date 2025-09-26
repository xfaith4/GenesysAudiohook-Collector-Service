#!/usr/bin/env python3
"""
Simple test for the AudioHook collector functionality
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from audiohook_collector import AudioHookCollector


class TestAudioHookCollector(unittest.TestCase):
    """Test AudioHook collector functionality"""

    def setUp(self):
        """Setup test environment"""
        # Create temporary output file
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl')
        self.temp_file.close()
        self.output_path = Path(self.temp_file.name)
        
        # Override environment variables for testing
        os.environ['OUTPUT_FILE'] = str(self.output_path)
        os.environ['CONSOLE_OUTPUT'] = 'false'
        os.environ['HTTP_PORT'] = '8078'  # Use different port for testing

    def tearDown(self):
        """Cleanup test environment"""
        if self.output_path.exists():
            self.output_path.unlink()

    def test_audiohook_event_detection(self):
        """Test AudioHook event detection logic"""
        collector = AudioHookCollector()
        
        # Test valid AudioHook event
        valid_event = {
            'eventEntity': {
                'id': 'AUDIOHOOK-0001',
                'name': 'AudioHook integration error',
                'description': 'The provisioned server URI is invalid.'
            },
            'conversationId': '34c18827-77a6-4970-ad66-6f2966c85bad',
            'entityType': 'integration'
        }
        
        self.assertTrue(collector.is_audiohook_event(valid_event))
        
        # Test invalid event
        invalid_event = {
            'eventEntity': {
                'id': 'SYSTEM-0001',
                'name': 'System event',
                'description': 'Regular system event'
            },
            'entityType': 'system'
        }
        
        self.assertFalse(collector.is_audiohook_event(invalid_event))

    def test_event_formatting(self):
        """Test event formatting"""
        collector = AudioHookCollector()
        collector.channel_id = 'test-channel-123'
        
        raw_event = {
            'eventEntity': {
                'id': 'AUDIOHOOK-0001',
                'name': 'AudioHook integration error',
                'description': 'The provisioned server URI is invalid.'
            },
            'conversationId': '34c18827-77a6-4970-ad66-6f2966c85bad',
            'entityType': 'integration',
            'entityId': '0f8f91f9-a27d-4ddf-9026-7e1e3a8d73a6',
            'entityName': 'AudioHook Integration Name',
            'version': '1.0'
        }
        
        formatted = collector.format_audiohook_event(raw_event, 'test.topic')
        
        # Check required fields
        self.assertEqual(formatted['event_id'], 'AUDIOHOOK-0001')
        self.assertEqual(formatted['event_name'], 'AudioHook integration error')
        self.assertEqual(formatted['conversation_id'], '34c18827-77a6-4970-ad66-6f2966c85bad')
        self.assertEqual(formatted['entity_type'], 'integration')
        self.assertEqual(formatted['topic'], 'test.topic')
        self.assertEqual(formatted['channel'], 'test-channel-123')
        self.assertEqual(formatted['event_type'], 'audiohook_operational')
        
        # Check raw event is preserved
        self.assertEqual(formatted['raw_event'], raw_event)

    def test_topic_loading(self):
        """Test topic loading logic"""
        collector = AudioHookCollector()
        
        # Check that predefined AudioHook topics exist in module constants
        from audiohook_collector import AUDIOHOOK_TOPICS
        
        expected_topics = [
            'platform.integration.audiohook',
            'platform.operations.audiohook',
            'v2.auditing.integration.audiohook'
        ]
        
        # The topics should be loaded from the default list
        # since we can't test API calls without credentials
        self.assertIn('platform.integration.audiohook', AUDIOHOOK_TOPICS)
        self.assertIn('platform.operations.audiohook', AUDIOHOOK_TOPICS)

    def test_file_rotation_logic(self):
        """Test file rotation functionality"""
        from audiohook_collector import rotate_file, MAX_FILE_SIZE
        
        # Create a test file
        test_file = Path(self.temp_file.name + '_rotation_test')
        
        # Write content larger than 1KB
        large_content = 'x' * 2048  # 2KB of content
        test_file.write_text(large_content)
        
        # File should exist and be large
        self.assertTrue(test_file.exists())
        self.assertGreater(test_file.stat().st_size, 2000)
        
        # Mock the rotation by calling it with a file that's "too big"
        # We'll temporarily override the MAX_FILE_SIZE check by calling with small size
        original_size = test_file.stat().st_size
        
        # Force rotation by making the max size smaller
        import audiohook_collector
        original_max = audiohook_collector.MAX_FILE_SIZE
        audiohook_collector.MAX_FILE_SIZE = 1024  # 1KB
        
        try:
            rotate_file(test_file)
            
            # Check if rotation happened 
            backup_file = test_file.with_suffix(f'{test_file.suffix}.1')
            
            # Either original file should not exist OR backup should exist
            rotation_occurred = backup_file.exists() or not test_file.exists()
            self.assertTrue(rotation_occurred, "File rotation should have occurred")
            
            # Cleanup
            if backup_file.exists():
                backup_file.unlink()
                
        finally:
            audiohook_collector.MAX_FILE_SIZE = original_max
            if test_file.exists():
                test_file.unlink()


def run_syntax_test():
    """Test that the collector can be imported and basic classes work"""
    try:
        collector = AudioHookCollector()
        print("✓ AudioHookCollector class can be instantiated")
        
        # Test basic methods
        test_event = {
            'eventEntity': {'id': 'AUDIOHOOK-0001'},
            'entityType': 'integration'
        }
        
        result = collector.is_audiohook_event(test_event)
        print(f"✓ Event detection works: {result}")
        
        collector.channel_id = 'test-123'
        formatted = collector.format_audiohook_event(test_event, 'test.topic')
        print(f"✓ Event formatting works, event_id: {formatted.get('event_id')}")
        
        print("✓ All syntax tests passed!")
        return True
        
    except Exception as e:
        print(f"✗ Syntax test failed: {e}")
        return False


if __name__ == '__main__':
    print("Running AudioHook Collector Tests...")
    
    # First run syntax test
    if not run_syntax_test():
        sys.exit(1)
    
    print("\nRunning unit tests...")
    
    # Run unit tests
    unittest.main(verbosity=2, exit=False)
    
    print("\nAll tests completed!")