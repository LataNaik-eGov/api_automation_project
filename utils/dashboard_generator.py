import json
import os
from datetime import datetime
import re

def parse_ids_file():
    """Parse the ids.txt file to extract created entities"""
    base_path = os.path.dirname(__file__)
    ids_file_path = os.path.join(base_path, "..", "output", "ids.txt")

    entities = {
        "Facility": [],
        "Household": [],
        "Individual": [],
        "Product": [],
        "Product Variant": [],
        "Project": [],
        "Project Resource": [],
        "Project Staff": [],
        "Project Facility": [],
        "Project Beneficiary": [],
        "Project Task": [],
        "Side Effect": [],
        "Referral": [],
        "HF Referral": [],
        "Localization": [],
        "Employee": [],
        "PGR Complaint": [],
        "Stock": []
    }

    try:
        with open(os.path.abspath(ids_file_path), 'r', encoding='utf-8') as f:
            content = f.read()

            # Extract Facility IDs
            facilities = re.findall(r'Facility ID: (F-[\d-]+)', content)
            entities["Facility"] = facilities

            # Extract Household IDs
            households = re.findall(r'Household ID: (H-[\d-]+)', content)
            entities["Household"] = households

            # Extract Individual IDs
            individuals = re.findall(r'Individual Ind ID: (IND-[\d-]+)', content)
            entities["Individual"] = individuals

            # Extract Product IDs
            products = re.findall(r'Product ID: (P-[\d-]+)', content)
            entities["Product"] = products

            # Extract Variant IDs
            variants = re.findall(r'Variant ID: (PVAR-[\d-]+)', content)
            entities["Product Variant"] = variants

            # Extract Project IDs (UUID format)
            projects = re.findall(r'Project ID: ([a-f0-9-]{36})', content)
            entities["Project"] = projects

            # Extract Project Resource IDs (deduplicate)
            project_resources = re.findall(r'Project Resource ID(?: \d)?: (PR-[\d-]+)', content)
            entities["Project Resource"] = list(dict.fromkeys(project_resources))

            # Extract Project Staff IDs
            project_staff = re.findall(r'Project Staff ID: (PTS-[\d-]+)', content)
            entities["Project Staff"] = project_staff

            # Extract Project Facility IDs (deduplicate)
            project_facilities = re.findall(r'Project Facility ID(?: \d)?: (PF-[\d-]+)', content)
            entities["Project Facility"] = list(dict.fromkeys(project_facilities))

            # Extract Project Beneficiary IDs
            project_beneficiaries = re.findall(r'Project Beneficiary ID: (PTB-[\d-]+)', content)
            entities["Project Beneficiary"] = project_beneficiaries

            # Extract Project Task IDs
            project_tasks = re.findall(r'Project Task ID: (PT-[\d-]+)', content)
            entities["Project Task"] = project_tasks

            # Extract Side Effect IDs (UUID format)
            side_effects = re.findall(r'Side Effect ID: ([a-f0-9-]{36})', content)
            entities["Side Effect"] = side_effects

            # Extract Referral IDs (UUID format)
            referrals = re.findall(r'Referral ID: ([a-f0-9-]{36})', content)
            entities["Referral"] = referrals

            # Extract HF Referral IDs (UUID format)
            hf_referrals = re.findall(r'HF Referral ID: ([a-f0-9-]{36})', content)
            entities["HF Referral"] = hf_referrals

            # Extract Localization Codes
            localization_codes = re.findall(r'Localization Code: ([\w_]+)', content)
            entities["Localization"] = localization_codes

            # Extract Employee Codes
            employee_codes = re.findall(r'Employee Code: ([\w-]+)', content)
            entities["Employee"] = employee_codes

            # Extract PGR Service Request IDs
            pgr_complaints = re.findall(r'Service Request ID: (PB-PGR-[\d-]+)', content)
            entities["PGR Complaint"] = pgr_complaints

            # Extract Stock IDs
            stocks = re.findall(r'Stock ID: (S-[\d-]+)', content)
            entities["Stock"] = stocks

    except Exception as e:
        print(f"Warning: Could not parse ids.txt: {e}")

    return entities

def parse_test_results():
    """Parse test results from JSON file"""
    base_path = os.path.dirname(__file__)
    results_file = os.path.join(base_path, "..", "output", "test_results.json")

    default_results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "tests": [],
        "start_time": None,
        "end_time": None
    }

    try:
        if os.path.exists(os.path.abspath(results_file)):
            with open(os.path.abspath(results_file), 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not parse test results: {e}")

    return default_results

def parse_created_campaigns():
    """Campaigns the console E2E created this run, from output/console/campaigns.json.

    Returned newest-first so the most recent run is at the top. Empty when the
    console suite has not run.
    """
    base_path = os.path.dirname(__file__)
    campaigns_file = os.path.join(base_path, "..", "output", "console", "campaigns.json")

    try:
        if not os.path.exists(os.path.abspath(campaigns_file)):
            return []
        with open(os.path.abspath(campaigns_file), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Warning: Could not parse created campaigns: {e}")
        return []

    campaigns = []
    for campaign_type, details in data.items():
        if not isinstance(details, dict):
            continue
        campaigns.append({
            "type": campaign_type,
            "name": details.get("campaignName", ""),
            "number": details.get("campaignNumber", ""),
            "id": details.get("campaignId", ""),
            "boundaries": details.get("boundaryCount", ""),
            "rows_filled": (details.get("excelIngestion") or {}).get("rowsFilled", ""),
        })
    return sorted(campaigns, key=lambda c: c["number"], reverse=True)


def count_operations(test_results):
    """Count create and search operations from test names"""
    operations = {
        "create": 0,
        "search": 0,
        "other": 0
    }

    for test in test_results.get("tests", []):
        test_name = test.get("name", "").lower()
        if "create" in test_name:
            operations["create"] += 1
        elif "search" in test_name:
            operations["search"] += 1
        else:
            operations["other"] += 1

    return operations

def get_service_name(test_name):
    """Extract service name from test file path (e.g., tests/test_household_service.py::test_name)"""
    test_name_lower = test_name.lower()

    # Extract service from test file name (more accurate than test function name)
    if "test_household_service" in test_name_lower:
        return "Household"
    elif "test_individual_service" in test_name_lower:
        return "Individual"
    elif "test_facility_service" in test_name_lower:
        return "Facility"
    elif "test_product_service" in test_name_lower:
        return "Product"
    elif "test_project_service" in test_name_lower:
        return "Project"
    elif "test_boundary_service" in test_name_lower:
        return "Boundary"
    elif "test_mdms_service" in test_name_lower:
        return "MDMS"
    elif "test_localization_service" in test_name_lower:
        return "Localization"
    elif "test_hrms_service" in test_name_lower:
        return "HRMS"
    elif "test_referralmanagement_service" in test_name_lower:
        return "Referral Management"
    elif "test_pgr_service" in test_name_lower:
        return "PGR"
    elif "test_stock_service" in test_name_lower:
        return "Stock"
    else:
        return "Other"


def get_service_breakdown(test_results):
    """Get test breakdown by service"""
    services = {}

    for test in test_results.get("tests", []):
        test_name = test.get("name", "")
        service = get_service_name(test_name)

        if service not in services:
            services[service] = {"passed": 0, "failed": 0, "total": 0}

        services[service]["total"] += 1
        if test.get("outcome") == "passed":
            services[service]["passed"] += 1
        elif test.get("outcome") == "failed":
            services[service]["failed"] += 1

    return services


def get_tests_by_service(test_results):
    """Group tests by service"""
    services = {}

    for test in test_results.get("tests", []):
        test_name = test.get("name", "")
        service = get_service_name(test_name)

        if service not in services:
            services[service] = []

        services[service].append(test)

    return services

def calculate_duration(start_time, end_time):
    """Calculate test execution duration"""
    if not start_time or not end_time:
        return "N/A"

    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
        duration = (end - start).total_seconds()
        return f"{duration:.2f}s"
    except:
        return "N/A"

def generate_dashboard():
    """Generate an interactive HTML dashboard"""
    entities = parse_ids_file()
    test_results = parse_test_results()
    created_campaigns = parse_created_campaigns()
    operations = count_operations(test_results)
    service_breakdown = get_service_breakdown(test_results)
    tests_by_service = get_tests_by_service(test_results)

    # Count entities
    entity_counts = {k: len(v) for k, v in entities.items()}
    total_entities = sum(entity_counts.values())

    # Calculate pass rate
    total_tests = test_results.get("total", 0)
    passed_tests = test_results.get("passed", 0)
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

    # Get timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duration = calculate_duration(test_results.get("start_time"), test_results.get("end_time"))

    if created_campaigns:
        campaign_rows = "".join(
            f"""
                        <tr>
                            <td><span class="badge badge-create">{c['type']}</span></td>
                            <td><strong class="campaign-name">{c['name']}</strong></td>
                            <td><code>{c['number']}</code></td>
                            <td><code class="campaign-id">{c['id']}</code></td>
                            <td>{c['boundaries']}</td>
                            <td>{c['rows_filled']}</td>
                        </tr>"""
            for c in created_campaigns
        )
        campaigns_section = f"""
        <!-- Campaigns created by the console E2E -->
        <div class="section">
            <h2>Campaigns Created</h2>
            <p class="section-hint">
                Created by <code>test_campaign_e2e.py</code> this run &mdash; look these up in
                the console under <em>My campaigns &rarr; Upcoming</em> to verify them by hand.
            </p>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Type</th><th>Campaign Name</th><th>Campaign Number</th>
                            <th>Campaign ID</th><th>Boundaries</th><th>Rows Filled</th>
                        </tr>
                    </thead>
                    <tbody>{campaign_rows}
                    </tbody>
                </table>
            </div>
        </div>
"""
    else:
        campaigns_section = ""

    # Generate HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Execution Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}

        .header {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
            text-align: center;
        }}

        .header h1 {{
            color: #667eea;
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        .header .timestamp {{
            color: #666;
            font-size: 1em;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            text-align: center;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}

        .stat-card .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 10px;
        }}

        .stat-card .stat-label {{
            font-size: 0.9em;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .section-hint {{ color: #666; font-size: 14px; margin: -8px 0 16px; }}
        .campaign-name {{ color: #c84c0c; font-size: 15px; }}
        .campaign-id {{ font-size: 12px; color: #777; }}
        .stat-card.success .stat-number {{ color: #28a745; }}
        .stat-card.danger .stat-number {{ color: #dc3545; }}
        .stat-card.info .stat-number {{ color: #667eea; }}
        .stat-card.warning .stat-number {{ color: #ffc107; }}

        .charts-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }}

        .chart-card {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}

        .chart-card h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.3em;
        }}

        .data-table {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            overflow-x: auto;
            margin-bottom: 30px;
        }}

        .data-table h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.3em;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
        }}

        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}

        th {{
            background: #f8f9fa;
            color: #667eea;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 1px;
        }}

        tr:hover {{
            background: #f8f9fa;
        }}

        .badge {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }}

        .badge-success {{ background: #d4edda; color: #155724; }}
        .badge-danger {{ background: #f8d7da; color: #721c24; }}
        .badge-info {{ background: #d1ecf1; color: #0c5460; }}
        .badge-warning {{ background: #fff3cd; color: #856404; }}

        .entity-id {{
            font-family: 'Courier New', monospace;
            background: #f0f0f0;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }}

        .progress-bar {{
            width: 100%;
            height: 25px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 0.85em;
        }}

        .collapsible-header {{
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
            transition: color 0.3s ease;
        }}

        .collapsible-header:hover {{
            color: #4c5fd5;
        }}

        .collapsible-header .toggle-icon {{
            font-size: 1.2em;
            transition: transform 0.3s ease;
        }}

        .collapsible-header.collapsed .toggle-icon {{
            transform: rotate(-90deg);
        }}

        .collapsible-content {{
            max-height: 50000px;
            overflow: visible;
            transition: max-height 0.5s ease-out;
        }}

        .collapsible-content.collapsed {{
            max-height: 0;
            overflow: hidden;
        }}

        .service-section {{
            margin-bottom: 15px;
            border: 1px solid #e9ecef;
            border-radius: 10px;
            overflow: hidden;
        }}

        .service-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
            transition: opacity 0.3s ease;
        }}

        .service-header:hover {{
            opacity: 0.9;
        }}

        .service-header h3 {{
            margin: 0;
            font-size: 1.1em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .service-header .service-stats {{
            display: flex;
            gap: 15px;
            align-items: center;
        }}

        .service-header .service-stats span {{
            font-size: 0.9em;
            padding: 4px 10px;
            border-radius: 15px;
            background: rgba(255,255,255,0.2);
        }}

        .service-header .toggle-icon {{
            font-size: 1em;
            transition: transform 0.3s ease;
        }}

        .service-header.collapsed .toggle-icon {{
            transform: rotate(-90deg);
        }}

        .service-tests {{
            max-height: 100000px;
            overflow: visible;
            transition: max-height 0.5s ease-out;
        }}

        .service-tests.collapsed {{
            max-height: 0;
            overflow: hidden;
        }}

        .service-tests table {{
            margin: 0;
        }}

        .service-tests th {{
            background: #f0f0f0;
        }}

        .test-row {{
            cursor: pointer;
        }}

        .test-row:hover {{
            background: #e8f4fc !important;
        }}

        .test-name {{
            font-family: monospace;
            font-size: 0.9em;
            color: #667eea;
            text-decoration: underline;
        }}

        .test-details {{
            display: none;
            background: #f8f9fa;
            border-top: 1px dashed #dee2e6;
        }}

        .test-details.show {{
            display: table-row;
        }}

        .test-details td {{
            padding: 15px 20px;
        }}

        .test-output {{
            background: linear-gradient(135deg, #f0f3ff 0%, #e8ecf8 100%);
            color: #4a5568;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            white-space: pre-wrap;
            word-wrap: break-word;
            max-height: 300px;
            overflow-y: auto;
            margin: 0;
        }}

        .test-output-label {{
            font-weight: 600;
            color: #667eea;
            margin-bottom: 8px;
            display: block;
        }}

        .test-error {{
            background: #fff5f5;
            border-left: 4px solid #dc3545;
            padding: 10px 15px;
            margin-top: 10px;
            border-radius: 0 8px 8px 0;
        }}

        .test-error pre {{
            color: #dc3545;
            margin: 0;
            white-space: pre-wrap;
            font-size: 0.85em;
        }}

        .no-output {{
            color: #6c757d;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Test Execution Dashboard</h1>
            <p class="timestamp">Generated: {timestamp}</p>
            <p class="timestamp">Duration: {duration}</p>
        </div>

        <!-- Test Execution Stats -->
        <div class="stats-grid">
            <div class="stat-card info">
                <div class="stat-number">{total_tests}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-card success">
                <div class="stat-number">{test_results.get('passed', 0)}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card danger">
                <div class="stat-number">{test_results.get('failed', 0)}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card warning">
                <div class="stat-number">{pass_rate:.1f}%</div>
                <div class="stat-label">Pass Rate</div>
            </div>
        </div>

        <!-- Operations Stats -->
        <div class="stats-grid">
            <div class="stat-card info">
                <div class="stat-number">{operations.get('create', 0)}</div>
                <div class="stat-label">Create Operations</div>
            </div>
            <div class="stat-card info">
                <div class="stat-number">{operations.get('search', 0)}</div>
                <div class="stat-label">Search Operations</div>
            </div>
            <div class="stat-card info">
                <div class="stat-number">{total_entities}</div>
                <div class="stat-label">Entities Created</div>
            </div>
            <div class="stat-card info">
                <div class="stat-number">{len(service_breakdown)}</div>
                <div class="stat-label">Services Tested</div>
            </div>
        </div>

        {campaigns_section}

        <!-- Charts -->
        <div class="charts-container">
            <div class="chart-card">
                <h2>📊 Test Results</h2>
                <canvas id="testResultsChart"></canvas>
            </div>
            <div class="chart-card">
                <h2>📈 Entities by Service</h2>
                <canvas id="entitiesChart"></canvas>
            </div>
            <div class="chart-card">
                <h2>🎯 Service Test Coverage</h2>
                <canvas id="serviceBreakdownChart"></canvas>
            </div>
        </div>

        <!-- Service Breakdown Table -->
        <div class="data-table">
            <h2>🏢 Service-wise Test Breakdown</h2>
            <table>
                <thead>
                    <tr>
                        <th>Service</th>
                        <th>Total Tests</th>
                        <th>Passed</th>
                        <th>Failed</th>
                        <th>Success Rate</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Add service breakdown rows
    for service, stats in service_breakdown.items():
        total = stats["total"]
        passed = stats["passed"]
        success_rate = (passed / total * 100) if total > 0 else 0

        html_content += f"""
                    <tr>
                        <td><span class="badge badge-info">{service}</span></td>
                        <td>{stats['total']}</td>
                        <td>{stats['passed']}</td>
                        <td>{stats['failed']}</td>
                        <td>{success_rate:.1f}%</td>
                    </tr>
"""

    html_content += """
                </tbody>
            </table>
        </div>

        <!-- Test Details Table (Grouped by Service) - Moved above Created Entities -->
        <div class="data-table">
            <div class="collapsible-header collapsed" onclick="toggleSection('testDetails')">
                <h2>📝 Test Execution Details (by Service)</h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div id="testDetails" class="collapsible-content collapsed">
"""

    # Add service-wise test sections
    service_icons = {
        "Individual": "👤",
        "Household": "🏠",
        "Facility": "🏢",
        "Product": "📦",
        "Project": "📋",
        "Boundary": "🗺️",
        "MDMS": "📊",
        "Localization": "🌐",
        "HRMS": "👔",
        "Referral Management": "🏥",
        "PGR": "📢",
        "Stock": "📦",
        "Other": "📁"
    }

    for service, tests in tests_by_service.items():
        service_id = service.lower().replace(" ", "_")
        passed_count = sum(1 for t in tests if t.get("outcome") == "passed")
        failed_count = sum(1 for t in tests if t.get("outcome") == "failed")
        total_count = len(tests)
        icon = service_icons.get(service, "📁")

        html_content += f"""
            <div class="service-section">
                <div class="service-header collapsed" onclick="toggleService('{service_id}')">
                    <h3>{icon} {service} Service</h3>
                    <div class="service-stats">
                        <span>Total: {total_count}</span>
                        <span style="background: rgba(40,167,69,0.3);">✓ {passed_count}</span>
                        <span style="background: rgba(220,53,69,0.3);">✗ {failed_count}</span>
                        <span class="toggle-icon">▼</span>
                    </div>
                </div>
                <div id="{service_id}" class="service-tests collapsed">
                    <table>
                        <thead>
                            <tr>
                                <th>Test Name</th>
                                <th>Status</th>
                                <th>Duration</th>
                            </tr>
                        </thead>
                        <tbody>
"""
        for idx, test in enumerate(tests):
            test_name = test.get("name", "Unknown").split("::")[-1]
            outcome = test.get("outcome", "unknown")
            duration = test.get("duration", 0)
            stdout = test.get("stdout", "")
            stderr = test.get("stderr", "")
            error = test.get("error", "")

            badge_class = "badge-success" if outcome == "passed" else "badge-danger" if outcome == "failed" else "badge-warning"
            status_icon = "✓" if outcome == "passed" else "✗" if outcome == "failed" else "⊘"

            # Unique ID for this test's details row
            test_id = f"{service_id}_test_{idx}"

            # Escape HTML characters in output
            stdout_escaped = stdout.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if stdout else ""
            stderr_escaped = stderr.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if stderr else ""
            error_escaped = error.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if error else ""

            html_content += f"""
                            <tr class="test-row" onclick="toggleTestDetails('{test_id}')">
                                <td class="test-name">{test_name}</td>
                                <td><span class="badge {badge_class}">{status_icon} {outcome.upper()}</span></td>
                                <td>{duration}s</td>
                            </tr>
                            <tr class="test-details" id="{test_id}">
                                <td colspan="3">
"""
            # Add stdout if available
            if stdout_escaped:
                html_content += f"""
                                    <span class="test-output-label">📤 Output:</span>
                                    <pre class="test-output">{stdout_escaped}</pre>
"""
            # Add stderr if available
            if stderr_escaped:
                html_content += f"""
                                    <span class="test-output-label">⚠️ Stderr:</span>
                                    <pre class="test-output" style="border-left: 3px solid #ffc107;">{stderr_escaped}</pre>
"""
            # Add error if available (for failed tests)
            if error_escaped:
                html_content += f"""
                                    <div class="test-error">
                                        <span class="test-output-label">❌ Error:</span>
                                        <pre>{error_escaped}</pre>
                                    </div>
"""
            # If no output at all
            if not stdout_escaped and not stderr_escaped and not error_escaped:
                html_content += """
                                    <span class="no-output">No output captured for this test.</span>
"""

            html_content += """
                                </td>
                            </tr>
"""

        html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
"""

    html_content += """
            </div>
        </div>

        <!-- Entities Table (Collapsible) -->
        <div class="data-table">
            <div class="collapsible-header collapsed" onclick="toggleSection('createdEntities')">
                <h2>🔖 Created Entities</h2>
                <span class="toggle-icon">▼</span>
            </div>
            <div id="createdEntities" class="collapsible-content collapsed">
                <table>
                    <thead>
                        <tr>
                            <th>Service</th>
                            <th>Entity ID</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    # Add entity rows
    for service, ids in entities.items():
        for entity_id in ids:
            html_content += f"""
                        <tr>
                            <td><span class="badge badge-info">{service}</span></td>
                            <td><span class="entity-id">{entity_id}</span></td>
                            <td><span class="badge badge-success">✓ Created</span></td>
                        </tr>
"""

    html_content += """
                    </tbody>
                </table>
            </div>
        </div>
    </div>
"""

    # Prepare chart data
    service_names = list(service_breakdown.keys())
    service_totals = [service_breakdown[s]["total"] for s in service_names]

    html_content += f"""

    <script>
        // Test Results Chart
        const testResultsCtx = document.getElementById('testResultsChart').getContext('2d');
        new Chart(testResultsCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['Passed', 'Failed', 'Skipped'],
                datasets: [{{
                    data: [{test_results.get('passed', 0)}, {test_results.get('failed', 0)}, {test_results.get('skipped', 0)}],
                    backgroundColor: [
                        'rgba(40, 167, 69, 0.8)',
                        'rgba(220, 53, 69, 0.8)',
                        'rgba(255, 193, 7, 0.8)'
                    ],
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});

        // Entities Chart
        const entitiesCtx = document.getElementById('entitiesChart').getContext('2d');
        new Chart(entitiesCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(list(entity_counts.keys()))},
                datasets: [{{
                    label: 'Entities Created',
                    data: {json.dumps(list(entity_counts.values()))},
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }}
            }}
        }});

        // Service Breakdown Chart
        const serviceBreakdownCtx = document.getElementById('serviceBreakdownChart').getContext('2d');
        new Chart(serviceBreakdownCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(service_names)},
                datasets: [{{
                    label: 'Tests Executed',
                    data: {json.dumps(service_totals)},
                    backgroundColor: 'rgba(118, 75, 162, 0.8)',
                    borderColor: 'rgba(118, 75, 162, 1)',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }}
            }}
        }});

        // Toggle collapsible section
        function toggleSection(sectionId) {{
            event.stopPropagation();
            const content = document.getElementById(sectionId);
            const header = content.previousElementSibling;

            content.classList.toggle('collapsed');
            header.classList.toggle('collapsed');
        }}

        // Toggle service section
        function toggleService(serviceId) {{
            event.stopPropagation();
            const content = document.getElementById(serviceId);
            const header = content.previousElementSibling;

            content.classList.toggle('collapsed');
            header.classList.toggle('collapsed');
        }}

        // Toggle test details
        function toggleTestDetails(testId) {{
            event.stopPropagation();
            const detailsRow = document.getElementById(testId);
            detailsRow.classList.toggle('show');
        }}
    </script>
</body>
</html>
"""

    # Write dashboard file
    base_path = os.path.dirname(__file__)
    dashboard_path = os.path.join(base_path, "..", "reports", "dashboard.html")

    os.makedirs(os.path.dirname(os.path.abspath(dashboard_path)), exist_ok=True)

    with open(os.path.abspath(dashboard_path), 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✓ Dashboard generated: {os.path.abspath(dashboard_path)}")
    return os.path.abspath(dashboard_path)

if __name__ == "__main__":
    dashboard_path = generate_dashboard()
    print(f"\nOpen the dashboard in your browser:")
    print(f"file://{dashboard_path}")
