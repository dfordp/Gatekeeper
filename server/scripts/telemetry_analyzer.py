# server/scripts/telemetry_analyzer.py
"""
Telemetry Analysis Tool - Phase 15

Command-line utility for deep analysis of telemetry data:
- Trace analysis and visualization
- Metric correlation and anomaly detection
- Alert trigger analysis
- Performance regression detection
- Report generation
"""

import asyncio
import sys
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.observability import TelemetryCollector, Alert, ServiceHealthTracker


class TelemetryAnalyzer:
    """Tool for analyzing telemetry data"""
    
    def __init__(self):
        """Initialize analyzer"""
        self.telemetry = TelemetryCollector()
        self.health = ServiceHealthTracker()
    
    async def initialize(self):
        """Initialize telemetry"""
        await self.telemetry.initialize()
    
    async def analyze_metrics(self, output_file: Optional[str] = None):
        """Analyze collected metrics"""
        print("\n" + "="*80)
        print("METRICS ANALYSIS")
        print("="*80 + "\n")
        
        summary = self.telemetry.get_metrics_summary()
        
        print(f"Total Metrics Collected: {summary['total_metrics']}")
        
        if summary['total_metrics'] > 0:
            print("\nMetric Names:")
            print("-" * 80)
            for i, metric_name in enumerate(summary['metrics'][:20], 1):
                print(f"  {i:2}. {metric_name}")
            
            if len(summary['metrics']) > 20:
                print(f"  ... and {len(summary['metrics']) - 20} more")
        
        print(f"\nAnalysis Timestamp: {summary['timestamp']}")
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(summary, f, indent=2)
            print(f"\n✓ Analysis saved to {output_file}")
    
    async def analyze_alerts(self, output_file: Optional[str] = None):
        """Analyze alert configuration and history"""
        print("\n" + "="*80)
        print("ALERTS ANALYSIS")
        print("="*80 + "\n")
        
        alerts = self.telemetry.alerts
        
        print(f"Total Alerts: {len(alerts)}\n")
        
        if alerts:
            severity_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
            
            for alert_name, alert in alerts.items():
                severity_counts[alert.severity] = severity_counts.get(alert.severity, 0) + 1
                
                status = "🟢 enabled" if alert.enabled else "🔴 disabled"
                print(f"  {status} {alert.name:<30} ({alert.severity.upper()})")
                print(f"      Condition: {alert.condition}")
                print(f"      Threshold: {alert.threshold}")
                print(f"      Triggered: {alert.triggered_count} times")
                if alert.last_triggered:
                    print(f"      Last Triggered: {alert.last_triggered.isoformat()}")
                print()
            
            print("\nSeverity Distribution:")
            print("-" * 80)
            for severity, count in severity_counts.items():
                if count > 0:
                    print(f"  {severity.upper():<10}: {count} alerts")
        else:
            print("  No alerts configured")
        
        if output_file:
            alert_data = {
                "total": len(alerts),
                "alerts": [
                    {
                        "name": alert.name,
                        "severity": alert.severity,
                        "condition": alert.condition,
                        "enabled": alert.enabled,
                        "triggered_count": alert.triggered_count
                    }
                    for alert in alerts.values()
                ]
            }
            with open(output_file, 'w') as f:
                json.dump(alert_data, f, indent=2)
            print(f"\n✓ Analysis saved to {output_file}")
    
    async def analyze_health(self, output_file: Optional[str] = None):
        """Analyze system health"""
        print("\n" + "="*80)
        print("SYSTEM HEALTH ANALYSIS")
        print("="*80 + "\n")
        
        health = self.health.get_overall_health()
        
        status_icon = "🟢" if health['status'] == 'healthy' else "🟡" if health['status'] == 'degraded' else "🔴"
        print(f"{status_icon} Overall Status: {health['status'].upper()}")
        print(f"  Healthy Checks: {health['healthy_count']}/{health['total_checks']}\n")
        
        if health['checks']:
            print("Component Health:")
            print("-" * 80)
            for component, check in health['checks'].items():
                check_status = "🟢 healthy" if check['status'] == 'healthy' else "🔴 unhealthy"
                print(f"  {check_status} {component:<20}")
                if 'latency_ms' in check:
                    print(f"      Latency: {check['latency_ms']:.2f} ms")
                if 'error' in check:
                    print(f"      Error: {check['error']}")
                print()
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(health, f, indent=2)
            print(f"✓ Analysis saved to {output_file}")
    
    async def generate_report(self, output_file: Optional[str] = None):
        """Generate comprehensive telemetry report"""
        print("\n" + "="*80)
        print("COMPREHENSIVE TELEMETRY REPORT")
        print(f"Generated: {datetime.now().isoformat()}")
        print("="*80 + "\n")
        
        # Telemetry Status
        print("📊 TELEMETRY STATUS")
        print("-" * 80)
        print(f"  Telemetry Enabled: {self.telemetry.enabled}")
        print(f"  Tracing: {'Active' if self.telemetry.tracer else 'Disabled'}")
        print(f"  Metrics: {'Active' if self.telemetry.meter else 'Disabled'}")
        print(f"  Logging: {'Active' if self.telemetry.logger_provider else 'Disabled'}\n")
        
        # Metrics Summary
        summary = self.telemetry.get_metrics_summary()
        print("📈 METRICS")
        print("-" * 80)
        print(f"  Total Metrics: {summary['total_metrics']}\n")
        
        # Alerts Summary
        alerts = self.telemetry.alerts
        print("🚨 ALERTS")
        print("-" * 80)
        print(f"  Total Configured: {len(alerts)}")
        enabled_count = sum(1 for a in alerts.values() if a.enabled)
        print(f"  Enabled: {enabled_count}")
        print(f"  Disabled: {len(alerts) - enabled_count}\n")
        
        # Health Summary
        health = self.health.get_overall_health()
        print("🏥 HEALTH")
        print("-" * 80)
        print(f"  Overall Status: {health['status'].upper()}")
        print(f"  Healthy Components: {health['healthy_count']}/{health['total_checks']}\n")
        
        # Recommendations
        print("💡 RECOMMENDATIONS")
        print("-" * 80)
        
        if summary['total_metrics'] < 10:
            print("  ⚠️  Low metric count - ensure metrics are being collected")
        elif summary['total_metrics'] > 1000:
            print("  ⚠️  High cardinality - review metric labeling strategy")
        else:
            print("  ✓ Metric collection appears balanced")
        
        if health['status'] == 'unhealthy':
            print("  ⚠️  System health issues detected - review status endpoints")
        else:
            print("  ✓ System health is good")
        
        if enabled_count == 0:
            print("  ⚠️  No alerts enabled - consider enabling critical alerts")
        else:
            print(f"  ✓ {enabled_count} alerts actively monitoring")
        
        if output_file:
            report = {
                "timestamp": datetime.now().isoformat(),
                "telemetry_status": {
                    "enabled": self.telemetry.enabled,
                    "tracing": "active" if self.telemetry.tracer else "disabled",
                    "metrics": "active" if self.telemetry.meter else "disabled",
                    "logging": "active" if self.telemetry.logger_provider else "disabled"
                },
                "metrics": summary,
                "alerts": {
                    "total": len(alerts),
                    "enabled": enabled_count,
                    "disabled": len(alerts) - enabled_count
                },
                "health": health
            }
            
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"\n✓ Full report saved to {output_file}")
    
    async def simulate_alert(self, alert_name: str):
        """Simulate an alert trigger"""
        print(f"\n" + "="*80)
        print(f"SIMULATING ALERT: {alert_name}")
        print("="*80 + "\n")
        
        if alert_name not in self.telemetry.alerts:
            print(f"❌ Alert '{alert_name}' not found")
            return
        
        alert = self.telemetry.alerts[alert_name]
        alert.triggered_count += 1
        alert.last_triggered = datetime.now()
        
        print(f"✓ Alert '{alert_name}' triggered")
        print(f"  Severity: {alert.severity.upper()}")
        print(f"  Total Triggers: {alert.triggered_count}")
        print(f"  Last Triggered: {alert.last_triggered.isoformat()}")
    
    async def run(self, command: str, *args):
        """Execute command"""
        await self.initialize()
        
        try:
            if command == "metrics":
                await self.analyze_metrics(args[0] if args else None)
            elif command == "alerts":
                await self.analyze_alerts(args[0] if args else None)
            elif command == "health":
                await self.analyze_health(args[0] if args else None)
            elif command == "report":
                await self.generate_report(args[0] if args else None)
            elif command == "simulate-alert":
                if not args:
                    print("Error: alert name required")
                    return
                await self.simulate_alert(args[0])
            else:
                print(f"Unknown command: {command}")
                self.print_usage()
        except Exception as e:
            print(f"Error: {e}")
    
    @staticmethod
    def print_usage():
        """Print usage information"""
        print("""
Telemetry Analysis Tool - Phase 15

Usage: python telemetry_analyzer.py <command> [options]

Commands:
  metrics [output_file]              Analyze collected metrics
  alerts [output_file]               Analyze alert configuration
  health [output_file]               Analyze system health
  report [output_file]               Generate comprehensive report
  simulate-alert <alert_name>        Simulate an alert trigger
  help                               Show this help message

Examples:
  python telemetry_analyzer.py metrics
  python telemetry_analyzer.py alerts alerts.json
  python telemetry_analyzer.py report system_report.json
  python telemetry_analyzer.py simulate-alert high_error_rate
        """)


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        TelemetryAnalyzer.print_usage()
        return
    
    command = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    if command == "help":
        TelemetryAnalyzer.print_usage()
        return
    
    analyzer = TelemetryAnalyzer()
    await analyzer.run(command, *args)


if __name__ == "__main__":
    asyncio.run(main())