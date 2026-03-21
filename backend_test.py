#!/usr/bin/env python3
"""
ViralForge v3 Backend API Testing Suite
Tests all endpoints for functionality and integration
"""
import requests
import json
import time
import sys
from datetime import datetime

class ViralForgeAPITester:
    def __init__(self, base_url="https://viral-forge-21.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name, method, endpoint, expected_status=200, data=None, timeout=30):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        self.tests_run += 1
        
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = self.session.get(url, timeout=timeout)
            elif method == 'POST':
                response = self.session.post(url, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ {name} - Status: {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except:
                    return True, response.text
            else:
                self.failed_tests.append({
                    'name': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:500]
                })
                self.log(f"❌ {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"Response: {response.text[:200]}", "ERROR")
                return False, {}

        except Exception as e:
            self.failed_tests.append({
                'name': name,
                'error': str(e),
                'endpoint': endpoint
            })
            self.log(f"❌ {name} - Error: {str(e)}", "ERROR")
            return False, {}

    def test_health_endpoint(self):
        """Test health endpoint"""
        success, response = self.run_test(
            "Health Check",
            "GET",
            "/api/health"
        )
        
        if success:
            # Verify required fields
            required_fields = ['ok', 'version', 'has_key']
            missing_fields = [f for f in required_fields if f not in response]
            if missing_fields:
                self.log(f"❌ Health endpoint missing fields: {missing_fields}", "FAIL")
                return False
            
            if not response.get('has_key'):
                self.log("⚠️  EMERGENT_LLM_KEY not configured", "WARN")
                return False
                
            self.log(f"✅ Health OK - Version: {response.get('version')}, Key: {response.get('has_key')}", "PASS")
            return True
        return False

    def test_stats_endpoint(self):
        """Test stats endpoint"""
        success, response = self.run_test(
            "Stats Endpoint",
            "GET",
            "/api/stats"
        )
        
        if success:
            expected_fields = ['trends_count', 'scripts_count', 'videos_count', 'fetch_status']
            missing_fields = [f for f in expected_fields if f not in response]
            if missing_fields:
                self.log(f"❌ Stats endpoint missing fields: {missing_fields}", "FAIL")
                return False
            self.log(f"✅ Stats - Trends: {response.get('trends_count', 0)}, Scripts: {response.get('scripts_count', 0)}", "PASS")
            return True
        return False

    def test_trends_fetch(self):
        """Test trends fetching"""
        self.log("Testing trends fetch (this may take 10-15 seconds)...")
        
        # Start fetch
        success, response = self.run_test(
            "Fetch Trends Start",
            "POST",
            "/api/trends/fetch",
            data={"categories": ["trending", "entertainment"], "force": False}
        )
        
        if not success:
            return False
            
        if response.get('status') not in ['started', 'already_running']:
            self.log(f"❌ Unexpected fetch response: {response}", "FAIL")
            return False
            
        # Poll for completion
        max_attempts = 30  # 30 seconds max
        for attempt in range(max_attempts):
            time.sleep(1)
            health_success, health_data = self.run_test(
                f"Health Check (Poll {attempt+1})",
                "GET",
                "/api/health"
            )
            
            if health_success:
                fetch_status = health_data.get('fetch_status', 'unknown')
                self.log(f"Fetch status: {fetch_status}")
                
                if fetch_status == 'done':
                    self.log("✅ Trends fetch completed successfully", "PASS")
                    return True
                elif 'error' in fetch_status:
                    self.log(f"❌ Trends fetch failed: {fetch_status}", "FAIL")
                    return False
                    
        self.log("❌ Trends fetch timed out", "FAIL")
        return False

    def test_trends_endpoints(self):
        """Test trends retrieval endpoints"""
        # Test trends list
        success, response = self.run_test(
            "Get Trends List",
            "GET",
            "/api/trends?limit=10"
        )
        
        if not success:
            return False
            
        trends = response.get('trends', [])
        if not trends:
            self.log("⚠️  No trends data available", "WARN")
            return True  # Not a failure if no data yet
            
        # Verify trend structure
        first_trend = trends[0]
        required_fields = ['id', 'title', 'virality_score', 'analysis']
        missing_fields = [f for f in required_fields if f not in first_trend]
        if missing_fields:
            self.log(f"❌ Trend object missing fields: {missing_fields}", "FAIL")
            return False
            
        self.log(f"✅ Retrieved {len(trends)} trends", "PASS")
        
        # Test patterns endpoint
        success, response = self.run_test(
            "Get Trends Patterns",
            "GET",
            "/api/trends/patterns"
        )
        
        return success

    def test_generation_pipeline(self):
        """Test the full AI generation pipeline"""
        self.log("Testing AI generation pipeline (this may take 30-60 seconds)...")
        
        success, response = self.run_test(
            "AI Generation Pipeline",
            "POST",
            "/api/generate",
            data={"niche": "tech"},
            timeout=90  # Longer timeout for AI generation
        )
        
        if not success:
            return False
            
        # Verify response structure
        required_fields = ['batch_id', 'script_id', 'options', 'winner', 'decision', 'script']
        missing_fields = [f for f in required_fields if f not in response]
        if missing_fields:
            self.log(f"❌ Generation response missing fields: {missing_fields}", "FAIL")
            return False
            
        options = response.get('options', [])
        if len(options) < 5:
            self.log(f"❌ Expected at least 5 options, got {len(options)}", "FAIL")
            return False
            
        winner = response.get('winner', {})
        if not winner.get('title') or not winner.get('hook'):
            self.log("❌ Winner missing title or hook", "FAIL")
            return False
            
        script = response.get('script', {})
        if not script.get('scenes') or len(script.get('scenes', [])) < 3:
            self.log("❌ Script missing scenes or too few scenes", "FAIL")
            return False
            
        self.log(f"✅ Generated {len(options)} ideas, winner selected, script created", "PASS")
        
        # Store script_id for video test
        self.script_id = response.get('script_id')
        self.test_script = script
        return True

    def test_scripts_endpoint(self):
        """Test scripts listing endpoint"""
        success, response = self.run_test(
            "List Scripts",
            "GET",
            "/api/scripts"
        )
        
        if success:
            scripts = response.get('scripts', [])
            self.log(f"✅ Retrieved {len(scripts)} scripts", "PASS")
            return True
        return False

    def test_video_generation(self):
        """Test video generation pipeline"""
        if not hasattr(self, 'script_id') or not hasattr(self, 'test_script'):
            self.log("⚠️  Skipping video test - no script available", "WARN")
            return True
            
        self.log("Testing video generation (this may take 60+ seconds)...")
        
        success, response = self.run_test(
            "Start Video Generation",
            "POST",
            "/api/video/generate",
            data={
                "script_id": self.script_id,
                "script": self.test_script,
                "palette": "amber"
            }
        )
        
        if not success:
            return False
            
        video_id = response.get('video_id')
        if not video_id:
            self.log("❌ No video_id returned", "FAIL")
            return False
            
        # Poll for video completion
        max_attempts = 120  # 2 minutes max
        for attempt in range(max_attempts):
            time.sleep(1)
            status_success, status_data = self.run_test(
                f"Video Status Check (Poll {attempt+1})",
                "GET",
                f"/api/video/status/{video_id}"
            )
            
            if status_success:
                status = status_data.get('status', 'unknown')
                progress = status_data.get('progress', 0)
                
                if attempt % 10 == 0:  # Log every 10 seconds
                    self.log(f"Video progress: {progress}% - {status}")
                
                if status == 'done' and status_data.get('video_ready'):
                    self.log("✅ Video generation completed successfully", "PASS")
                    self.test_video_id = video_id
                    return True
                elif status in ['failed', 'error']:
                    self.log(f"❌ Video generation failed: {status_data.get('message', '')}", "FAIL")
                    return False
                    
        self.log("❌ Video generation timed out", "FAIL")
        return False

    def test_videos_endpoints(self):
        """Test video listing and download endpoints"""
        success, response = self.run_test(
            "List Videos",
            "GET",
            "/api/videos"
        )
        
        if not success:
            return False
            
        videos = response.get('videos', [])
        self.log(f"✅ Retrieved {len(videos)} videos", "PASS")
        
        # Test download endpoint if we have a video
        if hasattr(self, 'test_video_id'):
            # Test download endpoint (just check if it responds, don't download)
            try:
                download_url = f"{self.base_url}/api/video/{self.test_video_id}/download"
                head_response = self.session.head(download_url, timeout=10)
                if head_response.status_code == 200:
                    self.log("✅ Video download endpoint accessible", "PASS")
                else:
                    self.log(f"❌ Video download failed: {head_response.status_code}", "FAIL")
            except Exception as e:
                self.log(f"❌ Video download test error: {e}", "FAIL")
                
        return True

    def run_all_tests(self):
        """Run all tests in sequence"""
        self.log("🚀 Starting ViralForge v3 Backend API Tests")
        self.log(f"Testing against: {self.base_url}")
        
        test_sequence = [
            ("Health Check", self.test_health_endpoint),
            ("Stats Endpoint", self.test_stats_endpoint),
            ("Trends Fetch", self.test_trends_fetch),
            ("Trends Endpoints", self.test_trends_endpoints),
            ("AI Generation Pipeline", self.test_generation_pipeline),
            ("Scripts Endpoint", self.test_scripts_endpoint),
            ("Video Generation", self.test_video_generation),
            ("Videos Endpoints", self.test_videos_endpoints),
        ]
        
        for test_name, test_func in test_sequence:
            self.log(f"\n{'='*50}")
            self.log(f"Running: {test_name}")
            self.log(f"{'='*50}")
            
            try:
                test_func()
            except Exception as e:
                self.log(f"❌ {test_name} crashed: {e}", "ERROR")
                self.failed_tests.append({
                    'name': test_name,
                    'error': f"Test crashed: {e}"
                })
        
        # Print summary
        self.print_summary()
        
        return self.tests_passed, self.tests_run, self.failed_tests

    def print_summary(self):
        """Print test summary"""
        self.log(f"\n{'='*60}")
        self.log("TEST SUMMARY")
        self.log(f"{'='*60}")
        self.log(f"Tests Run: {self.tests_run}")
        self.log(f"Tests Passed: {self.tests_passed}")
        self.log(f"Tests Failed: {len(self.failed_tests)}")
        self.log(f"Success Rate: {(self.tests_passed/max(self.tests_run,1)*100):.1f}%")
        
        if self.failed_tests:
            self.log(f"\n❌ FAILED TESTS:")
            for i, failure in enumerate(self.failed_tests, 1):
                self.log(f"{i}. {failure['name']}")
                if 'error' in failure:
                    self.log(f"   Error: {failure['error']}")
                if 'expected' in failure:
                    self.log(f"   Expected: {failure['expected']}, Got: {failure['actual']}")

def main():
    tester = ViralForgeAPITester()
    passed, total, failures = tester.run_all_tests()
    
    # Return appropriate exit code
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n💥 {len(failures)} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())