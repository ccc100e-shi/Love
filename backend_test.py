#!/usr/bin/env python3
"""
ViralForge v3 Backend API Testing Suite
Tests the simplified single-endpoint API
"""
import requests
import json
import time
import sys
from datetime import datetime

class ViralForgeV3Tester:
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

    def test_generate_all_endpoint(self):
        """Test the main generate-all endpoint"""
        self.log("Testing generate-all endpoint (this may take 30-60 seconds)...")
        
        # Test with valid prompt
        success, response = self.run_test(
            "Generate All - Valid Prompt",
            "POST",
            "/api/generate-all",
            data={"prompt": "Create a viral video about fitness motivation"},
            timeout=10  # Just test if it starts, don't wait for completion
        )
        
        if not success:
            return False
            
        # Verify response structure
        if 'job_id' not in response:
            self.log("❌ Generate-all response missing job_id", "FAIL")
            return False
            
        if response.get('status') != 'processing':
            self.log(f"❌ Expected status 'processing', got {response.get('status')}", "FAIL")
            return False
            
        self.log(f"✅ Generate-all started successfully - Job ID: {response.get('job_id')}", "PASS")
        self.test_job_id = response.get('job_id')
        
        # Test with invalid prompt (empty)
        success, response = self.run_test(
            "Generate All - Invalid Prompt",
            "POST",
            "/api/generate-all",
            expected_status=400,
            data={"prompt": ""}
        )
        
        if success:
            self.log("✅ Correctly rejected empty prompt", "PASS")
        
        return True

    def test_job_status_endpoint(self):
        """Test job status endpoint"""
        if not hasattr(self, 'test_job_id'):
            self.log("⚠️  Skipping job status test - no job_id available", "WARN")
            return True
            
        success, response = self.run_test(
            "Job Status Check",
            "GET",
            f"/api/job/{self.test_job_id}"
        )
        
        if not success:
            return False
            
        # Verify response structure
        required_fields = ['status', 'progress', 'step']
        missing_fields = [f for f in required_fields if f not in response]
        if missing_fields:
            self.log(f"❌ Job status missing fields: {missing_fields}", "FAIL")
            return False
            
        status = response.get('status')
        progress = response.get('progress', 0)
        step = response.get('step', '')
        
        self.log(f"✅ Job status: {status}, Progress: {progress}%, Step: {step}", "PASS")
        
        # Test invalid job ID
        success, response = self.run_test(
            "Job Status - Invalid ID",
            "GET",
            "/api/job/invalid-job-id",
            expected_status=404
        )
        
        if success:
            self.log("✅ Correctly returned 404 for invalid job ID", "PASS")
        
        return True

    def test_video_download_endpoint(self):
        """Test video download endpoint"""
        # Test with invalid video ID (should return 404)
        success, response = self.run_test(
            "Video Download - Invalid ID",
            "GET",
            "/api/video/invalid-video-id",
            expected_status=404
        )
        
        if success:
            self.log("✅ Correctly returned 404 for invalid video ID", "PASS")
            return True
        
        return False

    def test_full_generation_flow(self):
        """Test the complete generation flow"""
        if not hasattr(self, 'test_job_id'):
            self.log("⚠️  Skipping full flow test - no job_id available", "WARN")
            return True
            
        self.log("Testing full generation flow (this may take 60+ seconds)...")
        
        # Poll job status until completion or timeout
        max_attempts = 120  # 2 minutes max
        for attempt in range(max_attempts):
            time.sleep(1)
            
            success, response = self.run_test(
                f"Job Status Poll {attempt+1}",
                "GET",
                f"/api/job/{self.test_job_id}"
            )
            
            if not success:
                continue
                
            status = response.get('status')
            progress = response.get('progress', 0)
            step = response.get('step', '')
            
            if attempt % 10 == 0:  # Log every 10 seconds
                self.log(f"Generation progress: {progress}% - {step}")
            
            if status == 'complete':
                result = response.get('result')
                if not result:
                    self.log("❌ Job complete but no result", "FAIL")
                    return False
                    
                # Verify result structure
                required_sections = ['idea', 'script', 'video']
                missing_sections = [s for s in required_sections if s not in result]
                if missing_sections:
                    self.log(f"❌ Result missing sections: {missing_sections}", "FAIL")
                    return False
                
                # Check idea section
                idea = result.get('idea', {})
                if not idea.get('title') or not idea.get('hook'):
                    self.log("❌ Idea section missing title or hook", "FAIL")
                    return False
                
                # Check script section
                script = result.get('script', {})
                scenes = script.get('scenes', [])
                if len(scenes) < 3:
                    self.log(f"❌ Script has too few scenes: {len(scenes)}", "FAIL")
                    return False
                
                # Check video section
                video = result.get('video', {})
                video_id = video.get('id')
                if not video_id:
                    self.log("❌ Video section missing ID", "FAIL")
                    return False
                
                self.log("✅ Full generation flow completed successfully", "PASS")
                self.test_video_id = video_id
                
                # Test video download if available
                if video.get('ready') and video.get('url'):
                    download_success, _ = self.run_test(
                        "Video Download Test",
                        "GET",
                        video.get('url'),
                        expected_status=200
                    )
                    if download_success:
                        self.log("✅ Video download successful", "PASS")
                
                return True
                
            elif status == 'error':
                self.log(f"❌ Generation failed: {step}", "FAIL")
                return False
                
        self.log("❌ Generation flow timed out", "FAIL")
        return False

    def run_all_tests(self):
        """Run all tests in sequence"""
        self.log("🚀 Starting ViralForge v3 Backend API Tests")
        self.log(f"Testing against: {self.base_url}")
        
        test_sequence = [
            ("Health Check", self.test_health_endpoint),
            ("Generate All Endpoint", self.test_generate_all_endpoint),
            ("Job Status Endpoint", self.test_job_status_endpoint),
            ("Video Download Endpoint", self.test_video_download_endpoint),
            ("Full Generation Flow", self.test_full_generation_flow),
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
    tester = ViralForgeV3Tester()
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