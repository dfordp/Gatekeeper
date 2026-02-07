# server/scripts/load_test.py
"""
Load testing script for Gatekeeper platform using Locust
Run: locust -f scripts/load_test.py --host=http://localhost:8000
"""
import random
import time
from locust import HttpUser, task, between, events
from datetime import datetime

# Test data
VALID_TOKEN = None  # Will be populated during setup
BASE_COMPANY_ID = "550e8400-e29b-41d4-a716-446655440000"
BASE_USER_ID = "550e8400-e29b-41d4-a716-446655440001"
TICKET_IDS = []
SEARCH_QUERIES = [
    "database connection error",
    "slow performance",
    "authentication failed",
    "network timeout",
    "memory leak issue"
]


class GatekeeperUser(HttpUser):
    """Simulated Gatekeeper user for load testing"""
    
    wait_time = between(0.5, 2)  # Wait 0.5-2 seconds between requests
    
    def on_start(self):
        """Login and get auth token before starting tasks"""
        global VALID_TOKEN
        
        if VALID_TOKEN:
            self.token = VALID_TOKEN
            return
        
        # Login to get token
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@gatekeeper.local",
                "password": "admin123"
            }
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            VALID_TOKEN = self.token
        else:
            self.token = "invalid-token"
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    @task(4)  # Weight: 4 (40% of requests)
    def list_tickets(self):
        """List tickets with pagination"""
        offset = random.randint(0, 100)
        with self.client.get(
            f"/api/tickets?limit=20&offset={offset}",
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
                data = response.json()
                global TICKET_IDS
                if data.get("tickets"):
                    TICKET_IDS = [t["id"] for t in data.get("tickets", [])]
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(3)  # Weight: 3 (30% of requests)
    def search_tickets(self):
        """Search for tickets by query"""
        query = random.choice(SEARCH_QUERIES)
        with self.client.get(
            f"/api/tickets/search?q={query}&limit=10",
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(2)  # Weight: 2 (20% of requests)
    def get_ticket_details(self):
        """Get details for a specific ticket"""
        if not TICKET_IDS:
            return
        
        ticket_id = random.choice(TICKET_IDS)
        with self.client.get(
            f"/api/tickets/{ticket_id}",
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(1)  # Weight: 1 (10% of requests)
    def create_ticket(self):
        """Create a new ticket"""
        ticket_data = {
            "subject": f"Test Ticket {int(time.time())}",
            "description": "This is a load test ticket",
            "severity": "medium",
            "category": "technical"
        }
        
        with self.client.post(
            "/api/tickets",
            json=ticket_data,
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")


class AdminUser(HttpUser):
    """Simulated admin user for load testing"""
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """Login as admin"""
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@gatekeeper.local",
                "password": "admin123"
            }
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            self.token = "invalid-token"
    
    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    @task
    def get_dashboard_stats(self):
        """Get dashboard statistics"""
        with self.client.get(
            "/api/dashboard/stats",
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task
    def view_performance_metrics(self):
        """View performance metrics"""
        with self.client.get(
            "/api/performance/query-stats",
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")


# Event handlers for metrics collection
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts"""
    print(f"\n{'='*60}")
    print(f"Load Test Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops"""
    print(f"\n{'='*60}")
    print(f"Load Test Stopped: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Print summary
    stats = environment.stats
    print("\n=== LOAD TEST SUMMARY ===")
    print(f"Total Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Failure Rate: {(stats.total.num_failures / max(stats.total.num_requests, 1)) * 100:.2f}%")
    print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"Min Response Time: {stats.total.min_response_time:.2f}ms")
    print(f"Max Response Time: {stats.total.max_response_time:.2f}ms")
    print(f"Median Response Time: {stats.total.median_response_time:.2f}ms")
    print(f"95th Percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
    print(f"99th Percentile: {stats.total.get_response_time_percentile(0.99):.2f}ms")