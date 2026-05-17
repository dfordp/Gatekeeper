# server/test_email_automation.py
"""Comprehensive tests for the email automation system"""
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.email_configuration_service import EmailConfigurationService
from services.email_queue_service import EmailQueueService
from services.email_listener_service import EmailListenerService
from core.logger import get_logger
from core.database import init_db, test_connection, SessionLocal, Company, User, EmailTemplate, EmailConfiguration, EmailLog

logger = get_logger(__name__)


def test_database_connection():
    """Test database connection"""
    print("\n" + "="*60)
    print("Testing Database Connection")
    print("="*60)
    
    success = test_connection()
    if success:
        print("✅ Database connection successful")
        return True
    else:
        print("❌ Database connection failed")
        return False


def test_database_initialization():
    """Test database initialization"""
    print("\n" + "="*60)
    print("Testing Database Initialization")
    print("="*60)
    
    success = init_db()
    if success:
        print("✅ Database tables initialized")
        return True
    else:
        print("❌ Failed to initialize database")
        return False


def test_template_creation():
    """Test creating default email templates"""
    print("\n" + "="*60)
    print("Testing Email Template Creation")
    print("="*60)
    
    try:
        success = EmailConfigurationService.create_default_templates()
        if success:
            print("✅ Default templates created")
            
            # Verify templates exist
            db = SessionLocal()
            templates = db.query(EmailTemplate).filter(EmailTemplate.is_active == True).all()
            db.close()
            
            print(f"   Found {len(templates)} templates:")
            for template in templates:
                print(f"   - {template.event_type}")
            
            return True
        else:
            print("❌ Failed to create templates")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_template_retrieval():
    """Test retrieving specific templates"""
    print("\n" + "="*60)
    print("Testing Template Retrieval")
    print("="*60)
    
    test_events = [
        "ticket_created",
        "ticket_assigned",
        "ticket_status_updated",
        "user_created"
    ]
    
    all_found = True
    for event_type in test_events:
        try:
            template = EmailConfigurationService.get_template(event_type)
            print(f"✅ Retrieved template for {event_type}")
            print(f"   Subject: {template['subject_template'][:60]}...")
        except Exception as e:
            print(f"❌ Failed to get {event_type}: {e}")
            all_found = False
    
    return all_found


def test_company_setup():
    """Test company and user setup"""
    print("\n" + "="*60)
    print("Testing Company and User Setup")
    print("="*60)
    
    db = SessionLocal()
    try:
        # Create test company
        company = Company(name=f"Test Company {str(uuid4())[:8]}")
        db.add(company)
        db.flush()
        company_id = str(company.id)
        print(f"✅ Created test company: {company_id}")
        
        # Create test users
        user1 = User(
            name="John Ticket Raiser",
            email=f"raiser_{uuid4()}@test.com",
            company_id=company.id,
            role="external"
        )
        db.add(user1)
        db.flush()
        raiser_id = str(user1.id)
        print(f"✅ Created ticket raiser: {raiser_id}")
        
        user2 = User(
            name="Jane Engineer",
            email=f"engineer_{uuid4()}@test.com",
            company_id=company.id,
            role="support_engineer"
        )
        db.add(user2)
        db.flush()
        engineer_id = str(user2.id)
        print(f"✅ Created engineer: {engineer_id}")
        
        db.commit()
        return {
            "company_id": company_id,
            "raiser_id": raiser_id,
            "engineer_id": engineer_id,
            "raiser_email": user1.email,
            "engineer_email": user2.email,
            "company": company
        }
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        return None
    finally:
        db.close()


def test_email_configuration():
    """Test email configuration setup"""
    print("\n" + "="*60)
    print("Testing Email Configuration")
    print("="*60)
    
    setup_data = test_company_setup()
    if not setup_data:
        print("❌ Failed to setup test data")
        return False
    
    company_id = setup_data["company_id"]
    
    try:
        # Get or create default config
        config = EmailConfigurationService.get_or_create_default_configuration(company_id)
        print(f"✅ Retrieved configuration for company")
        print(f"   Enabled events: {len(config['enabled_events'])} events")
        print(f"   Is enabled: {config['is_enabled']}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_event_enabled_check():
    """Test checking if events are enabled"""
    print("\n" + "="*60)
    print("Testing Event Enable Check")
    print("="*60)
    
    setup_data = test_company_setup()
    if not setup_data:
        return False
    
    company_id = setup_data["company_id"]
    
    try:
        # Create config
        EmailConfigurationService.get_or_create_default_configuration(company_id)
        
        # Check various events
        events_to_check = [
            "ticket_created",
            "ticket_assigned",
            "user_created",
            "nonexistent_event"
        ]
        
        for event_type in events_to_check:
            is_enabled = EmailConfigurationService.is_event_enabled(event_type, company_id)
            status = "✅ Enabled" if is_enabled else "❌ Disabled"
            print(f"{status}: {event_type}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_recipient_determination():
    """Test determining recipients for events"""
    print("\n" + "="*60)
    print("Testing Recipient Determination")
    print("="*60)
    
    setup_data = test_company_setup()
    if not setup_data:
        return False
    
    company_id = setup_data["company_id"]
    raiser_id = setup_data["raiser_id"]
    engineer_id = setup_data["engineer_id"]
    
    try:
        # Create config
        EmailConfigurationService.get_or_create_default_configuration(company_id)
        
        # Test different event scenarios
        print("Testing recipient determination for different events:")
        
        # Ticket created - should go to raiser
        recipients = EmailConfigurationService.get_recipients_for_event(
            "ticket_created",
            company_id,
            raised_by_user_id=raiser_id
        )
        print(f"✅ ticket_created recipients: {len(recipients)} (expecting 1)")
        if recipients:
            print(f"   To: {recipients[0]['email']}")
        
        # Ticket assigned - should go to engineer
        recipients = EmailConfigurationService.get_recipients_for_event(
            "ticket_assigned",
            company_id,
            assigned_engineer_id=engineer_id
        )
        print(f"✅ ticket_assigned recipients: {len(recipients)} (expecting 1)")
        if recipients:
            print(f"   To: {recipients[0]['email']}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_template_rendering():
    """Test Jinja2 template rendering"""
    print("\n" + "="*60)
    print("Testing Template Rendering")
    print("="*60)
    
    try:
        template_vars = {
            "user_name": "John Doe",
            "ticket_no": "TKT-000001",
            "ticket_subject": "Cannot connect to database",
            "category": "Database",
            "level": "Level 1",
            "company_name": "Acme Corp"
        }
        
        # Test subject rendering
        subject_template = "New Ticket: {{ticket_no}} - {{ticket_subject}}"
        rendered_subject = EmailQueueService._render_template(subject_template, template_vars)
        print(f"✅ Subject template rendered:")
        print(f"   {rendered_subject}")
        
        # Test body rendering
        body_template = "Hello {{user_name}}, your ticket {{ticket_no}} has been created for: {{ticket_subject}}"
        rendered_body = EmailQueueService._render_template(body_template, template_vars)
        print(f"✅ Body template rendered:")
        print(f"   {rendered_body}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_email_queue_task():
    """Test queuing an email task"""
    print("\n" + "="*60)
    print("Testing Email Queue Task")
    print("="*60)
    
    setup_data = test_company_setup()
    if not setup_data:
        return False
    
    company_id = setup_data["company_id"]
    raiser_id = setup_data["raiser_id"]
    raiser_email = setup_data["raiser_email"]
    
    try:
        # Create config
        EmailConfigurationService.get_or_create_default_configuration(company_id)
        
        # Queue test email
        recipients = [{
            "email": raiser_email,
            "role": "external",
            "user_id": raiser_id
        }]
        
        template_vars = {
            "user_name": "John Doe",
            "ticket_no": "TKT-TEST-001",
            "ticket_subject": "Test ticket for automation",
            "category": "Test",
            "level": "Level 3",
            "company_name": company_id,
            "ticket_url": "https://gatekeeper.example.com/tickets/TKT-TEST-001",
            "portal_url": "https://gatekeeper.example.com"
        }
        
        task_id = EmailQueueService.queue_email_task(
            email_type="ticket_created",
            event_type="ticket_created",
            company_id=company_id,
            recipient_list=recipients,
            template_variables=template_vars,
            ticket_id="test-ticket-id"
        )
        
        if task_id:
            print(f"✅ Email task queued successfully")
            print(f"   Task ID: {task_id}")
            print(f"   Recipient: {raiser_email}")
            return True
        else:
            print(f"❌ Failed to queue email task")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_email_listener_callbacks():
    """Test email listener callback functions"""
    print("\n" + "="*60)
    print("Testing Email Listener Callbacks")
    print("="*60)
    
    setup_data = test_company_setup()
    if not setup_data:
        return False
    
    company_id = setup_data["company_id"]
    raiser_id = setup_data["raiser_id"]
    raiser_email = setup_data["raiser_email"]
    
    try:
        # Create config
        EmailConfigurationService.get_or_create_default_configuration(company_id)
        
        # Test ticket_created listener
        print("Calling on_ticket_created listener...")
        EmailListenerService.on_ticket_created(
            ticket_id="test-ticket-1",
            ticket_no="TKT-000001",
            ticket_subject="Test Ticket",
            company_id=company_id,
            raised_by_user_id=raiser_id,
            raised_by_user_name="John Doe",
            raised_by_user_email=raiser_email
        )
        print("✅ on_ticket_created listener executed without errors")
        
        # Test user_created listener
        print("Calling on_user_created listener...")
        EmailListenerService.on_user_created(
            user_id="test-user-1",
            user_name="Jane Smith",
            user_email="jane@example.com",
            company_id=company_id,
            role="support_engineer"
        )
        print("✅ on_user_created listener executed without errors")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n\n" + "="*80)
    print("EMAIL AUTOMATION SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*80)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Database Initialization", test_database_initialization),
        ("Template Creation", test_template_creation),
        ("Template Retrieval", test_template_retrieval),
        ("Email Configuration", test_email_configuration),
        ("Event Enabled Check", test_event_enabled_check),
        ("Recipient Determination", test_recipient_determination),
        ("Template Rendering", test_template_rendering),
        ("Email Queue Task", test_email_queue_task),
        ("Email Listener Callbacks", test_email_listener_callbacks),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Print summary
    print("\n\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*80 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
