import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import anthropic

app = FastAPI(title="Lush Construction AI Quote Manager")
templates = Jinja2Templates(directory="templates")

# Initialize Claude client
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# Load mock data
def load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

projects_db = load_json("data/projects.json")
subcontractors_db = load_json("data/subcontractors.json")
historical_quotes_db = load_json("data/historical_quotes.json")
quotes_db = load_json("data/active_quotes.json")

def save_json(data, filepath):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def get_trade_price_range(trade_name):
    """Get realistic price range for a trade type"""
    price_ranges = {
        "Electrical": {"min": 8000, "max": 18000},
        "Plumbing": {"min": 6000, "max": 14000},
        "HVAC": {"min": 7000, "max": 16000},
        "Foundation/Concrete": {"min": 12000, "max": 25000},
        "Roofing": {"min": 8000, "max": 20000},
        "Insulation": {"min": 3000, "max": 7000},
        "Drywall/Finishing": {"min": 5000, "max": 12000},
        "Flooring": {"min": 4000, "max": 15000},
        "Kitchen": {"min": 8000, "max": 25000},
        "Bathroom Fixtures": {"min": 3000, "max": 8000},
        "Siding/Trim": {"min": 6000, "max": 18000},
        "Windows/Doors": {"min": 5000, "max": 15000},
        "Painting": {"min": 3000, "max": 8000},
        "Landscaping": {"min": 2000, "max": 10000},
        "Site Utilities": {"min": 4000, "max": 12000}
    }
    return price_ranges.get(trade_name, {"min": 2000, "max": 15000})

async def identify_trades_with_ai(project_description, rfp_content):
    """Use Claude to identify required trades from project description and RFP"""
    if not anthropic_client.api_key:
        # Fallback for demo without API key
        return [
            "Electrical", "Plumbing", "HVAC", "Foundation/Concrete", 
            "Roofing", "Insulation", "Drywall/Finishing", "Flooring",
            "Kitchen", "Windows/Doors", "Painting"
        ]
    
    system_prompt = """You are an expert construction project manager specializing in 3D-printed and modular home construction. Analyze project descriptions and RFP documents to identify all required trade specialties.

Return ONLY a JSON array of trade names from this standard list:
["Electrical", "Plumbing", "HVAC", "Foundation/Concrete", "Roofing", "Insulation", "Drywall/Finishing", "Flooring", "Kitchen", "Bathroom Fixtures", "Siding/Trim", "Windows/Doors", "Painting", "Landscaping", "Site Utilities", "Permits/Inspections", "Solar", "Smart Home/Security", "Garage Doors"]

Example response: ["Electrical", "Plumbing", "HVAC", "Roofing"]"""
    
    user_content = f"""Project: {project_description}

RFP Details: {rfp_content}

Identify all required trades for this construction project."""

    try:
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}]
        )
        
        content = response.content[0].text.strip()
        # Extract JSON array from response
        if content.startswith('[') and content.endswith(']'):
            return json.loads(content)
        else:
            # Try to find JSON array in the text
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
    except Exception as e:
        print(f"AI trade identification failed: {e}")
    
    # Fallback trades for demo
    return ["Electrical", "Plumbing", "HVAC", "Foundation/Concrete", "Roofing", "Drywall/Finishing", "Flooring"]

def generate_quote_responses(project_id, trades):
    """Generate realistic quote responses from subcontractors"""
    responses = []
    
    for trade in trades:
        # Get subcontractors for this trade
        trade_subs = [sub for sub in subcontractors_db.get("subcontractors", []) 
                     if trade.lower() in [spec.lower() for spec in sub.get("specialties", [])]]
        
        if not trade_subs:
            continue
            
        # Select 2-4 preferred subcontractors
        preferred_subs = [sub for sub in trade_subs if sub.get("preferred", False)]
        selected_subs = preferred_subs[:3] if len(preferred_subs) >= 3 else trade_subs[:3]
        
        price_range = get_trade_price_range(trade)
        
        for sub in selected_subs:
            # Simulate response timing (some respond faster)
            response_delay = random.randint(0, 72)  # 0-72 hours
            response_time = datetime.now() + timedelta(hours=response_delay)
            
            # Generate quote price with some variation
            base_price = random.randint(price_range["min"], price_range["max"])
            # Add 10% variation for different subs
            price_variation = random.uniform(0.9, 1.1)
            quote_price = int(base_price * price_variation)
            
            # Simulate different response statuses
            status_weights = [("received", 0.7), ("pending", 0.2), ("followed_up", 0.1)]
            status = random.choices([s[0] for s in status_weights], 
                                  weights=[s[1] for s in status_weights])[0]
            
            response = {
                "quote_id": f"Q{project_id}-{trade[:3].upper()}-{sub['id']}",
                "project_id": project_id,
                "trade": trade,
                "subcontractor_id": sub["id"],
                "subcontractor_name": sub["name"],
                "quote_price": quote_price,
                "status": status,
                "requested_at": (datetime.now() - timedelta(hours=random.randint(6, 48))).isoformat(),
                "response_time": response_time.isoformat() if status != "received" else datetime.now().isoformat(),
                "communication_method": sub.get("preferred_contact", "email"),
                "notes": f"Standard {trade.lower()} package for modular construction",
                "is_anomaly": abs(quote_price - base_price) > (base_price * 0.15)  # Flag 15%+ variance
            }
            responses.append(response)
    
    return responses

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Get recent projects and quote summaries
    projects = projects_db.get("projects", [])
    quotes = quotes_db.get("quotes", [])
    
    # Calculate summary metrics
    total_projects = len(projects)
    total_quotes_sent = len(quotes)
    quotes_received = len([q for q in quotes if q["status"] == "received"])
    anomalies_flagged = len([q for q in quotes if q.get("is_anomaly", False)])
    
    # Get recent activity (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    recent_quotes = [q for q in quotes if datetime.fromisoformat(q["requested_at"].replace('Z', '')) > week_ago]
    
    context = {
        "request": request,
        "projects": projects[:5],  # Show 5 most recent
        "recent_quotes": recent_quotes[:10],
        "total_projects": total_projects,
        "total_quotes_sent": total_quotes_sent,
        "quotes_received": quotes_received,
        "anomalies_flagged": anomalies_flagged,
        "response_rate": f"{(quotes_received / max(total_quotes_sent, 1) * 100):.1f}%"
    }
    
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/project/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str):
    # Find the project
    project = None
    for p in projects_db.get("projects", []):
        if p["id"] == project_id:
            project = p
            break
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get quotes for this project
    project_quotes = [q for q in quotes_db.get("quotes", []) if q["project_id"] == project_id]
    
    # Group quotes by trade
    quotes_by_trade = {}
    for quote in project_quotes:
        trade = quote["trade"]
        if trade not in quotes_by_trade:
            quotes_by_trade[trade] = []
        quotes_by_trade[trade].append(quote)
    
    context = {
        "request": request,
        "project": project,
        "quotes_by_trade": quotes_by_trade,
        "total_quotes": len(project_quotes),
        "received_quotes": len([q for q in project_quotes if q["status"] == "received"])
    }
    
    return templates.TemplateResponse("project_detail.html", context)

@app.post("/create-project", response_class=HTMLResponse)
async def create_project(
    request: Request,
    project_name: str = Form(...),
    project_description: str = Form(...),
    rfp_details: str = Form(...)
):
    # Generate new project ID
    project_id = f"LUSH-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"
    
    # Use AI to identify required trades
    identified_trades = await identify_trades_with_ai(project_description, rfp_details)
    
    # Create new project
    new_project = {
        "id": project_id,
        "name": project_name,
        "description": project_description,
        "rfp_details": rfp_details,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "required_trades": identified_trades,
        "estimated_timeline": "8-12 weeks",
        "project_manager": "RJ Lange"
    }
    
    # Add to projects database
    if "projects" not in projects_db:
        projects_db["projects"] = []
    projects_db["projects"].insert(0, new_project)
    save_json(projects_db, "data/projects.json")
    
    # Generate quote responses
    quote_responses = generate_quote_responses(project_id, identified_trades)
    
    # Add quotes to database
    if "quotes" not in quotes_db:
        quotes_db["quotes"] = []
    quotes_db["quotes"].extend(quote_responses)
    save_json(quotes_db, "data/quotes.json")
    
    # Redirect to project detail
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/project/{project_id}", status_code=303)

@app.get("/quotes/anomalies", response_class=HTMLResponse)
async def anomalies_dashboard(request: Request):
    quotes = quotes_db.get("quotes", [])
    anomalous_quotes = [q for q in quotes if q.get("is_anomaly", False) and q["status"] == "received"]
    
    # Add historical comparison
    for quote in anomalous_quotes:
        trade = quote["trade"]
        historical = [h for h in historical_quotes_db.get("historical_quotes", []) if h["trade"] == trade]
        if historical:
            avg_price = sum(h["price"] for h in historical) / len(historical)
            quote["historical_avg"] = avg_price
            quote["variance_pct"] = ((quote["quote_price"] - avg_price) / avg_price) * 100
        else:
            quote["historical_avg"] = quote["quote_price"]
            quote["variance_pct"] = 0
    
    context = {
        "request": request,
        "anomalous_quotes": anomalous_quotes
    }
    
    return templates.TemplateResponse("anomalies.html", context)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)