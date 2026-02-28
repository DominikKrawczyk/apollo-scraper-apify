"""
HTML parsing functions for extracting data from Apollo.io pages.
Handles different page types: search results, company profiles, contact profiles.

*** FIXED VERSION — broader selectors for Apollo's actual DOM ***
"""

from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
import re
import json
from datetime import datetime
from src.utils import log_message


def parse_search_results(html: str) -> List[Dict[str, Any]]:
    """
    Parse Apollo search results page to extract lead/company data.
    
    Args:
        html: HTML content of search results page
    
    Returns:
        List of dictionaries containing extracted data
    """
    soup = BeautifulSoup(html, 'lxml')
    results = []
    
    # =========================================================================
    # FIX: Apollo uses dynamically-generated class names with prefixes like
    # "zp_" or hashed names. The old regex selectors were too specific.
    # We now try multiple strategies from most-specific to broadest.
    # =========================================================================
    
    result_items = []
    
    # Strategy 1: Apollo's table rows (most common for people search)
    # Apollo renders people search as a <table> with <tbody><tr> rows
    tables = soup.find_all('table')
    for table in tables:
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
            if rows:
                log_message(f"Strategy 1 (table tbody tr): Found {len(rows)} rows", 'DEBUG')
                result_items = rows
                break
    
    # Strategy 2: Try data-cy attributes (Apollo uses these for testing)
    if not result_items:
        result_items = soup.find_all(attrs={'data-cy': re.compile(r'contact|person|people|result|row', re.I)})
        if result_items:
            log_message(f"Strategy 2 (data-cy): Found {len(result_items)} items", 'DEBUG')
    
    # Strategy 3: Apollo's zp_ prefixed classes on table rows
    if not result_items:
        result_items = soup.find_all('tr', class_=re.compile(r'zp_'))
        if result_items:
            log_message(f"Strategy 3 (zp_ class tr): Found {len(result_items)} items", 'DEBUG')
    
    # Strategy 4: Look for divs with role="row" (accessible table patterns)
    if not result_items:
        result_items = soup.find_all(attrs={'role': 'row'})
        if result_items:
            log_message(f"Strategy 4 (role=row): Found {len(result_items)} items", 'DEBUG')
    
    # Strategy 5: Old-style class-based selectors (original code)
    if not result_items:
        result_items = (
            soup.find_all('tr', class_=re.compile(r'.*person.*row.*', re.I)) or
            soup.find_all('div', class_=re.compile(r'.*search.*result.*item.*', re.I)) or
            soup.find_all('div', {'data-cy': re.compile(r'.*person.*')})
        )
        if result_items:
            log_message(f"Strategy 5 (legacy selectors): Found {len(result_items)} items", 'DEBUG')
    
    # Strategy 6: Broadest fallback — any tr inside any table on the page
    # Skip header rows (usually the first tr or tr inside thead)
    if not result_items:
        all_trs = soup.find_all('tr')
        # Filter out header rows
        result_items = [tr for tr in all_trs if not tr.find_parent('thead') and tr.find('td')]
        if result_items:
            log_message(f"Strategy 6 (all non-header tr): Found {len(result_items)} items", 'DEBUG')
    
    log_message(f"Found {len(result_items)} result items on page", 'DEBUG')
    
    for item in result_items:
        try:
            result = extract_contact_from_element(item)
            if result:
                results.append(result)
        except Exception as e:
            log_message(f"Error parsing result item: {e}", 'DEBUG')
            continue
    
    # =========================================================================
    # Strategy 7: If HTML parsing found nothing, try extracting from
    # Apollo's embedded JSON data (React state / Next.js data)
    # =========================================================================
    if not results:
        log_message("⚠️  No results from HTML parsing, trying JSON extraction...", 'DEBUG')
        json_results = extract_from_embedded_json(html)
        if json_results:
            log_message(f"✅ JSON extraction found {len(json_results)} results", 'DEBUG')
            results = json_results
    
    return results


def extract_from_embedded_json(html: str) -> List[Dict[str, Any]]:
    """
    Try to extract contact data from Apollo's embedded JSON / React state.
    Apollo sometimes embeds search results as JSON in script tags.
    
    Args:
        html: Full page HTML
        
    Returns:
        List of contact dicts, or empty list
    """
    results = []
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        
        # Look for script tags containing JSON data with contact info
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.string or ''
            
            # Look for patterns that suggest contact data
            if not any(kw in script_text for kw in ['people', 'contacts', 'person', 'email_status']):
                continue
            
            # Try to find JSON objects in the script
            # Apollo often uses window.__APOLLO_STATE__ or similar
            json_patterns = [
                r'window\.__APOLLO_STATE__\s*=\s*({.*?});',
                r'window\.__NEXT_DATA__\s*=\s*({.*?});',
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                r'"contacts":\s*(\[.*?\])',
                r'"people":\s*(\[.*?\])',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, script_text, re.DOTALL)
                for match in matches:
                    try:
                        data = json.loads(match)
                        # Try to extract contacts from the parsed JSON
                        contacts = _extract_contacts_from_json(data)
                        results.extend(contacts)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        log_message(f"JSON extraction failed: {e}", 'DEBUG')
    
    return results


def _extract_contacts_from_json(data: Any, depth: int = 0) -> List[Dict[str, Any]]:
    """Recursively search JSON structure for contact-like objects"""
    contacts = []
    
    if depth > 5:  # Prevent infinite recursion
        return contacts
    
    if isinstance(data, dict):
        # Check if this dict looks like a contact
        has_name = any(k in data for k in ['name', 'first_name', 'firstName', 'full_name'])
        has_email = any(k in data for k in ['email', 'email_address', 'emailAddress'])
        has_title = any(k in data for k in ['title', 'headline', 'job_title', 'jobTitle'])
        
        if has_name and (has_email or has_title):
            contact = {
                'type': 'contact',
                'scraped_at': datetime.now().isoformat(),
                'name': data.get('name') or data.get('first_name', '') + ' ' + data.get('last_name', ''),
                'first_name': data.get('first_name') or data.get('firstName', ''),
                'last_name': data.get('last_name') or data.get('lastName', ''),
                'title': data.get('title') or data.get('headline') or data.get('job_title', ''),
                'company': data.get('organization_name') or data.get('company') or data.get('company_name', ''),
                'email': data.get('email') or data.get('email_address', ''),
                'phone': data.get('phone') or data.get('phone_number', ''),
                'location': data.get('city', '') + (', ' + data.get('state', '') if data.get('state') else ''),
                'linkedin_url': data.get('linkedin_url') or data.get('linkedin', ''),
                'profile_url': None,
                'source': 'json_extraction',
            }
            # Clean empty string location
            if contact['location'].strip() == ',':
                contact['location'] = ''
            contacts.append(contact)
        else:
            # Recurse into dict values
            for v in data.values():
                contacts.extend(_extract_contacts_from_json(v, depth + 1))
    
    elif isinstance(data, list):
        for item in data:
            contacts.extend(_extract_contacts_from_json(item, depth + 1))
    
    return contacts


def extract_contact_from_element(element) -> Optional[Dict[str, Any]]:
    """
    Extract contact information from a single search result element.
    
    Args:
        element: BeautifulSoup element containing contact data
    
    Returns:
        Dictionary with contact information
    """
    contact = {
        'type': 'contact',
        'scraped_at': datetime.now().isoformat()
    }
    
    # =========================================================================
    # FIX: Get ALL text cells first for fallback extraction
    # Apollo tables have <td> cells; we can extract by column position
    # =========================================================================
    cells = element.find_all('td')
    all_links = element.find_all('a', href=True)
    
    # Extract name - try multiple selectors
    name_elem = (
        element.find('a', class_=re.compile(r'.*name.*', re.I)) or
        element.find('div', class_=re.compile(r'.*name.*', re.I)) or
        element.find('span', class_=re.compile(r'.*name.*', re.I))
    )
    
    # Fallback: first link in the row that points to /people/ is usually the name
    if not name_elem:
        for link in all_links:
            href = link.get('href', '')
            if '/people/' in href or '/contacts/' in href:
                name_elem = link
                break
    
    # Fallback: first <td> with a link is often the name cell
    if not name_elem and cells:
        first_link_in_cell = cells[0].find('a') if cells else None
        if first_link_in_cell:
            name_elem = first_link_in_cell
    
    contact['name'] = clean_text(name_elem.get_text()) if name_elem else ''
    
    # Extract title/position
    title_elem = (
        element.find('div', class_=re.compile(r'.*title.*', re.I)) or
        element.find('span', class_=re.compile(r'.*title.*', re.I))
    )
    # Fallback: title is usually in the 2nd or 3rd <td> cell
    if not title_elem and len(cells) >= 2:
        # Look for a cell that contains typical title keywords
        for cell in cells[1:4]:
            cell_text = clean_text(cell.get_text())
            if cell_text and not '@' in cell_text and len(cell_text) > 2:
                # Skip if it looks like a company name (has a company link)
                if not cell.find('a', href=re.compile(r'/companies/')):
                    title_elem = cell
                    break
    
    contact['title'] = clean_text(title_elem.get_text()) if title_elem else ''
    
    # Extract company
    company_elem = (
        element.find('a', href=re.compile(r'/companies/')) or
        element.find('a', class_=re.compile(r'.*company.*', re.I)) or
        element.find('div', class_=re.compile(r'.*company.*', re.I))
    )
    contact['company'] = clean_text(company_elem.get_text()) if company_elem else ''
    
    # Extract location
    location_elem = element.find('div', class_=re.compile(r'.*location.*', re.I))
    if not location_elem:
        # Look for text with city, state pattern in later cells
        for cell in cells[2:] if cells else []:
            cell_text = clean_text(cell.get_text())
            # Match patterns like "San Francisco, CA" or "New York, US"
            if re.search(r'\w+,\s*\w{2,}', cell_text) and '@' not in cell_text:
                location_elem = cell
                break
    contact['location'] = clean_text(location_elem.get_text()) if location_elem else ''
    
    # Extract email - may be hidden/locked on free accounts
    email_elem = (
        element.find('a', href=re.compile(r'^mailto:')) or
        element.find('span', class_=re.compile(r'.*email.*', re.I))
    )
    # Fallback: look for @ symbol in any cell
    if not email_elem:
        for cell in cells if cells else []:
            cell_text = cell.get_text()
            if '@' in cell_text:
                email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', cell_text)
                if email_match:
                    contact['email'] = email_match.group()
                    email_elem = True  # Flag to skip below
                break
    
    if email_elem and not contact.get('email'):
        if hasattr(email_elem, 'get') and email_elem.get('href'):
            contact['email'] = email_elem.get('href').replace('mailto:', '')
        elif hasattr(email_elem, 'get_text'):
            email_text = email_elem.get_text()
            if '@' in email_text:
                contact['email'] = clean_text(email_text)
            else:
                contact['email'] = 'locked'  # Email hidden by free account
    elif not contact.get('email'):
        contact['email'] = None
    
    # Extract phone
    phone_elem = element.find(string=re.compile(r'[\+\(\)0-9\-\s]{10,}'))
    contact['phone'] = clean_text(str(phone_elem)) if phone_elem else None
    
    # Extract LinkedIn URL
    linkedin_elem = element.find('a', href=re.compile(r'linkedin\.com'))
    contact['linkedin_url'] = linkedin_elem.get('href') if linkedin_elem else None
    
    # Extract profile URL
    profile_link = (
        element.find('a', href=re.compile(r'/people/')) or
        element.find('a', href=re.compile(r'/contacts/'))
    )
    if profile_link:
        href = profile_link.get('href', '')
        if href.startswith('http'):
            contact['profile_url'] = href
        else:
            contact['profile_url'] = 'https://app.apollo.io' + href
    else:
        contact['profile_url'] = None
    
    # Only return if we got a name (essential field)
    return contact if contact['name'] else None


def parse_contact_profile(html: str) -> Dict[str, Any]:
    """
    Parse individual contact profile page for detailed information.
    
    Args:
        html: HTML content of contact profile page
    
    Returns:
        Dictionary with detailed contact information
    """
    soup = BeautifulSoup(html, 'lxml')
    
    profile = {
        'type': 'contact_profile',
        'scraped_at': datetime.now().isoformat()
    }
    
    # Extract name from header
    name_elem = soup.find('h1') or soup.find('div', class_=re.compile(r'.*name.*header.*', re.I))
    profile['name'] = clean_text(name_elem.get_text()) if name_elem else ''
    
    # Extract title
    title_elem = soup.find('div', class_=re.compile(r'.*title.*', re.I))
    profile['title'] = clean_text(title_elem.get_text()) if title_elem else ''
    
    # Extract company information
    company_elem = soup.find('a', href=re.compile(r'/companies/'))
    if company_elem:
        profile['company'] = clean_text(company_elem.get_text())
        href = company_elem.get('href', '')
        profile['company_url'] = ('https://app.apollo.io' + href) if not href.startswith('http') else href
    else:
        profile['company'] = ''
        profile['company_url'] = None
    
    # Extract location
    location_elem = soup.find(string=re.compile(r'.*\w+,\s*\w+.*'))
    profile['location'] = clean_text(str(location_elem)) if location_elem else ''
    
    # Extract emails - may be multiple
    profile['emails'] = extract_emails(soup)
    
    # Extract phones - may be multiple
    profile['phones'] = extract_phones(soup)
    
    # Extract social links
    profile['social_links'] = extract_social_links(soup)
    
    # Extract bio/summary
    bio_elem = soup.find('div', class_=re.compile(r'.*bio.*|.*summary.*', re.I))
    profile['bio'] = clean_text(bio_elem.get_text()) if bio_elem else ''
    
    # Extract experience/work history
    profile['experience'] = extract_experience(soup)
    
    # Extract education
    profile['education'] = extract_education(soup)
    
    # Extract technologies/skills
    profile['technologies'] = extract_technologies(soup)
    
    return profile


def parse_company_profile(html: str) -> Dict[str, Any]:
    """
    Parse company profile page for detailed company information.
    
    Args:
        html: HTML content of company profile page
    
    Returns:
        Dictionary with company information
    """
    soup = BeautifulSoup(html, 'lxml')
    
    company = {
        'type': 'company_profile',
        'scraped_at': datetime.now().isoformat()
    }
    
    # Extract company name
    name_elem = soup.find('h1') or soup.find('div', class_=re.compile(r'.*company.*name.*', re.I))
    company['name'] = clean_text(name_elem.get_text()) if name_elem else ''
    
    # Extract website
    website_elem = soup.find('a', class_=re.compile(r'.*website.*', re.I))
    company['website'] = website_elem.get('href') if website_elem else None
    
    # Extract industry
    industry_elem = soup.find(string=re.compile(r'Industry', re.I))
    if industry_elem:
        industry_value = industry_elem.find_next('div') or industry_elem.find_next('span')
        company['industry'] = clean_text(industry_value.get_text()) if industry_value else ''
    else:
        company['industry'] = ''
    
    # Extract employee count
    employee_elem = soup.find(string=re.compile(r'Employees|Employee Count', re.I))
    if employee_elem:
        employee_value = employee_elem.find_next('div') or employee_elem.find_next('span')
        company['employee_count'] = clean_text(employee_value.get_text()) if employee_value else ''
    else:
        company['employee_count'] = ''
    
    # Extract revenue
    revenue_elem = soup.find(string=re.compile(r'Revenue', re.I))
    if revenue_elem:
        revenue_value = revenue_elem.find_next('div') or revenue_elem.find_next('span')
        company['revenue'] = clean_text(revenue_value.get_text()) if revenue_value else ''
    else:
        company['revenue'] = ''
    
    # Extract location/headquarters
    location_elem = soup.find(string=re.compile(r'Headquarters|Location', re.I))
    if location_elem:
        location_value = location_elem.find_next('div') or location_elem.find_next('span')
        company['headquarters'] = clean_text(location_value.get_text()) if location_value else ''
    else:
        company['headquarters'] = ''
    
    # Extract founded year
    founded_elem = soup.find(string=re.compile(r'Founded', re.I))
    if founded_elem:
        founded_value = founded_elem.find_next('div') or founded_elem.find_next('span')
        company['founded'] = clean_text(founded_value.get_text()) if founded_value else ''
    else:
        company['founded'] = ''
    
    # Extract description
    desc_elem = soup.find('div', class_=re.compile(r'.*description.*', re.I))
    company['description'] = clean_text(desc_elem.get_text()) if desc_elem else ''
    
    # Extract technologies
    company['technologies'] = extract_technologies(soup)
    
    # Extract social links
    company['social_links'] = extract_social_links(soup)
    
    # Extract phone numbers
    company['phones'] = extract_phones(soup)
    
    # Extract funding information
    company['funding'] = extract_funding_info(soup)
    
    return company


def extract_emails(soup) -> List[str]:
    """Extract all visible email addresses from page"""
    emails = []
    
    # Find mailto links
    mailto_links = soup.find_all('a', href=re.compile(r'^mailto:'))
    for link in mailto_links:
        email = link.get('href').replace('mailto:', '')
        if email and email != 'locked':
            emails.append(email)
    
    # Find text that looks like emails
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    all_text = soup.get_text()
    found_emails = re.findall(email_pattern, all_text)
    emails.extend(found_emails)
    
    return list(set(emails))  # Remove duplicates


def extract_phones(soup) -> List[str]:
    """Extract all visible phone numbers from page"""
    phones = []
    
    # Find tel links
    tel_links = soup.find_all('a', href=re.compile(r'^tel:'))
    for link in tel_links:
        phone = link.get('href').replace('tel:', '')
        phones.append(phone)
    
    # Find text that looks like phone numbers
    phone_pattern = r'[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,9}'
    phone_elems = soup.find_all(string=re.compile(phone_pattern))
    for elem in phone_elems:
        phone_match = re.search(phone_pattern, str(elem))
        if phone_match:
            phones.append(phone_match.group())
    
    return list(set([clean_text(p) for p in phones]))


def extract_social_links(soup) -> Dict[str, str]:
    """Extract social media profile links"""
    social = {}
    
    # LinkedIn
    linkedin = soup.find('a', href=re.compile(r'linkedin\.com/in/'))
    if linkedin:
        social['linkedin'] = linkedin.get('href')
    
    # Twitter
    twitter = soup.find('a', href=re.compile(r'twitter\.com/|x\.com/'))
    if twitter:
        social['twitter'] = twitter.get('href')
    
    # Facebook
    facebook = soup.find('a', href=re.compile(r'facebook\.com/'))
    if facebook:
        social['facebook'] = facebook.get('href')
    
    # GitHub
    github = soup.find('a', href=re.compile(r'github\.com/'))
    if github:
        social['github'] = github.get('href')
    
    return social


def extract_experience(soup) -> List[Dict[str, str]]:
    """Extract work experience/employment history"""
    experience = []
    
    exp_section = soup.find('div', class_=re.compile(r'.*experience.*', re.I))
    if exp_section:
        job_items = exp_section.find_all('div', class_=re.compile(r'.*job.*|.*position.*', re.I))
        for job in job_items:
            exp_data = {
                'title': '',
                'company': '',
                'duration': '',
                'description': ''
            }
            
            title_elem = job.find('div', class_=re.compile(r'.*title.*', re.I))
            if title_elem:
                exp_data['title'] = clean_text(title_elem.get_text())
            
            company_elem = job.find('div', class_=re.compile(r'.*company.*', re.I))
            if company_elem:
                exp_data['company'] = clean_text(company_elem.get_text())
            
            duration_elem = job.find('div', class_=re.compile(r'.*duration.*|.*date.*', re.I))
            if duration_elem:
                exp_data['duration'] = clean_text(duration_elem.get_text())
            
            if exp_data['title'] or exp_data['company']:
                experience.append(exp_data)
    
    return experience


def extract_education(soup) -> List[Dict[str, str]]:
    """Extract education history"""
    education = []
    
    edu_section = soup.find('div', class_=re.compile(r'.*education.*', re.I))
    if edu_section:
        edu_items = edu_section.find_all('div', class_=re.compile(r'.*school.*|.*degree.*', re.I))
        for item in edu_items:
            edu_data = {
                'school': '',
                'degree': '',
                'field': '',
                'years': ''
            }
            
            school_elem = item.find('div', class_=re.compile(r'.*school.*|.*university.*', re.I))
            if school_elem:
                edu_data['school'] = clean_text(school_elem.get_text())
            
            degree_elem = item.find('div', class_=re.compile(r'.*degree.*', re.I))
            if degree_elem:
                edu_data['degree'] = clean_text(degree_elem.get_text())
            
            if edu_data['school'] or edu_data['degree']:
                education.append(edu_data)
    
    return education


def extract_technologies(soup) -> List[str]:
    """Extract technologies/tools/skills used"""
    technologies = []
    
    tech_section = soup.find('div', class_=re.compile(r'.*technolog.*|.*tech.*stack.*', re.I))
    if tech_section:
        tech_items = tech_section.find_all(['span', 'div'], class_=re.compile(r'.*tag.*|.*badge.*|.*chip.*', re.I))
        for item in tech_items:
            tech_name = clean_text(item.get_text())
            if tech_name and len(tech_name) > 1:
                technologies.append(tech_name)
    
    return list(set(technologies))


def extract_funding_info(soup) -> Dict[str, Any]:
    """Extract funding/investment information for companies"""
    funding = {
        'total_funding': '',
        'last_funding_round': '',
        'investors': []
    }
    
    funding_section = soup.find('div', class_=re.compile(r'.*funding.*', re.I))
    if funding_section:
        total_elem = funding_section.find(string=re.compile(r'Total Funding', re.I))
        if total_elem:
            total_value = total_elem.find_next('div') or total_elem.find_next('span')
            funding['total_funding'] = clean_text(total_value.get_text()) if total_value else ''
        
        round_elem = funding_section.find(string=re.compile(r'Last.*Round|Latest.*Round', re.I))
        if round_elem:
            round_value = round_elem.find_next('div') or round_elem.find_next('span')
            funding['last_funding_round'] = clean_text(round_value.get_text()) if round_value else ''
    
    return funding


def clean_text(text: str) -> str:
    """
    Clean extracted text by removing extra whitespace and special characters.
    
    Args:
        text: Raw text to clean
    
    Returns:
        Cleaned text
    """
    if not text:
        return ''
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Remove common UI artifacts
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def detect_page_type(html: str) -> str:
    """
    Detect the type of Apollo page from HTML content.
    
    Args:
        html: HTML content
    
    Returns:
        Page type: 'search', 'contact_profile', 'company_profile', or 'unknown'
    """
    soup = BeautifulSoup(html, 'lxml')
    html_lower = html.lower()
    
    # =========================================================================
    # FIX: Much broader detection — check for multiple indicators
    # Apollo's class names are dynamic/hashed, so we also check page content
    # =========================================================================
    
    # Check for search results indicators
    search_indicators = [
        # DOM-based
        soup.find('div', class_=re.compile(r'.*search.*results.*', re.I)),
        soup.find('table', class_=re.compile(r'zp_', re.I)),
        soup.find(attrs={'data-cy': re.compile(r'contacts-table|people-table|search', re.I)}),
        soup.find('div', class_=re.compile(r'.*finder.*results.*', re.I)),
        soup.find('div', class_=re.compile(r'.*ContactTable.*|.*PeopleTable.*', re.I)),
        # Content-based: if there's a table with multiple rows, it's probably search
        len(soup.find_all('tr')) > 3,
    ]
    if any(search_indicators):
        return 'search'
    
    # Check for contact profile indicators
    contact_indicators = [
        soup.find('div', class_=re.compile(r'.*person.*profile.*', re.I)),
        soup.find('div', class_=re.compile(r'.*contact.*detail.*', re.I)),
        # URL pattern embedded in page
        'contacts/people' in html_lower or '/people/' in html_lower,
    ]
    # Only match contact_profile if NOT search (people links appear in search too)
    if any(contact_indicators) and not any(search_indicators):
        return 'contact_profile'
    
    # Check for company profile indicators
    company_indicators = [
        soup.find('div', class_=re.compile(r'.*company.*profile.*', re.I)),
        soup.find('div', class_=re.compile(r'.*org.*detail.*', re.I)),
    ]
    if any(company_indicators):
        return 'company_profile'
    
    return 'unknown'
