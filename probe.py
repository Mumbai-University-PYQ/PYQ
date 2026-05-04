import cloudscraper
import os
import json
import re
from pathlib import Path
from urllib.parse import urljoin
import time

BASE_URL = "https://www.munotes.in/question-papers/"
DOWNLOAD_DIR = os.path.expanduser("~/Study/munotes_backup")

# Initialize cloudscraper to handle Cloudflare
scraper = cloudscraper.create_scraper()

def get_page_html(url):
    """Fetch page HTML bypassing Cloudflare"""
    try:
        print(f"  [*] Fetching: {url}")
        response = scraper.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [-] Error fetching {url}: {e}")
        return None

def extract_links_from_html(html, base_url):
    """Extract all href links from HTML"""
    links = []
    
    # Find all href attributes
    href_pattern = r'href=["\']([^"\']+)["\']'
    for match in re.finditer(href_pattern, html):
        href = match.group(1)
        if href.startswith('http'):
            links.append(href)
        elif href.startswith('/'):
            links.append(urljoin(base_url, href))
        elif not href.startswith('#') and href.strip():
            links.append(urljoin(base_url, href))
    
    return list(set(links))

def extract_pdf_urls_from_html(html, base_url):
    """Extract PDF URLs from HTML - both href and data attributes"""
    pdf_urls = []
    
    # Pattern 1: Direct PDF links in href attributes
    href_pattern = r'href=["\']([^"\']*\.pdf[^"\']*)["\']'
    for match in re.finditer(href_pattern, html, re.IGNORECASE):
        url = match.group(1)
        if url.startswith('http'):
            pdf_urls.append(url)
        else:
            pdf_urls.append(urljoin(base_url, url))
    
    # Pattern 2: PDF URLs in data attributes or JavaScript
    data_pattern = r'(?:data-url|data-pdf|src)=["\']([^"\']*\.pdf[^"\']*)["\']'
    for match in re.finditer(data_pattern, html, re.IGNORECASE):
        url = match.group(1)
        if url.startswith('http'):
            pdf_urls.append(url)
        else:
            pdf_urls.append(urljoin(base_url, url))
    
    # Pattern 3: Extract from JavaScript object literals or API responses embedded in HTML
    # Look for patterns like: "url": "...pdf", "pdfUrl": "...pdf", etc.
    json_pattern = r'["\'](?:url|pdfUrl|pdf_url|fileUrl|download_url)["\']?\s*:\s*["\']([^"\']*\.pdf[^"\']*)["\']'
    for match in re.finditer(json_pattern, html, re.IGNORECASE):
        url = match.group(1)
        if url.startswith('http'):
            pdf_urls.append(url)
        else:
            pdf_urls.append(urljoin(base_url, url))
    
    # Pattern 4: Look for /uploads/ paths that lead to PDFs
    upload_pattern = r'["\']([^"\']*?/uploads/[^"\']*\.pdf[^"\']*)["\']'
    for match in re.finditer(upload_pattern, html, re.IGNORECASE):
        url = match.group(1)
        if url.startswith('http'):
            pdf_urls.append(url)
        else:
            pdf_urls.append(urljoin(base_url, url))
    
    return list(set(pdf_urls))

def get_course_list():
    """Get all 48 courses from main page"""
    html = get_page_html(BASE_URL)
    if not html:
        return []
    
    links = extract_links_from_html(html, BASE_URL)
    courses = []
    
    for link in links:
        # Filter for course-level links (exactly one level deep: /question-papers/COURSE-NAME/)
        if '/question-papers/' in link and link.count('/question-papers/') == 1:
            # Ensure it ends with a slash
            if not link.endswith('/'):
                link += '/'
            if link != BASE_URL:
                courses.append(link)
    
    return sorted(list(set(courses)))

def get_semesters(course_url):
    """Get all semesters for a course"""
    html = get_page_html(course_url)
    if not html:
        return []
    
    links = extract_links_from_html(html, course_url)
    sems = [link for link in links if '/Sem' in link]
    return sorted(list(set(sems)))

def get_years(semester_url):
    """Get all year folders for a semester"""
    html = get_page_html(semester_url)
    if not html:
        return []
    
    links = extract_links_from_html(html, semester_url)
    # Filter for year folders (2022-2023, ATKT, etc.)
    years = [link for link in links if re.search(r'\d{4}[-\s_]\d{4}|ATKT', link)]
    return sorted(list(set(years)))

def get_pdfs_for_year(year_url):
    """Get PDF URLs for a specific year"""
    html = get_page_html(year_url)
    if not html:
        return []
    
    pdfs = extract_pdf_urls_from_html(html, year_url)
    return list(set(pdfs))

def download_pdf(pdf_url, save_path):
    """Download a single PDF file"""
    try:
        response = scraper.get(pdf_url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Check if it's actually a PDF
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type and response.content[:4] != b'%PDF':
            print(f"    [-] Not a PDF (Content-Type: {content_type})")
            return False
        
        # Create directory if needed
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # Download with progress
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        percent = (downloaded / total_size) * 100
                        print(f"    [{percent:.1f}%] {os.path.basename(save_path)}", end='\r')
        
        print(f"    [✓] Downloaded: {os.path.basename(save_path)}")
        return True
        
    except Exception as e:
        print(f"    [-] Failed to download: {e}")
        return False

def list_courses_interactive():
    """List all courses and let user select one"""
    print("[*] Fetching all available courses...")
    courses = get_course_list()
    
    if not courses:
        print("[-] No courses found!")
        return None
    
    print(f"\n[+] Found {len(courses)} courses:\n")
    for idx, course_url in enumerate(courses, 1):
        course_name = course_url.rstrip('/').split('/')[-1]
        print(f"  [{idx:2d}] {course_name}")
    
    print()
    while True:
        try:
            choice = input("[*] Enter course number (or 'q' to quit): ").strip()
            if choice.lower() == 'q':
                return None
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(courses):
                selected_course = courses[choice_num - 1]
                selected_name = selected_course.rstrip('/').split('/')[-1]
                print(f"\n[✓] Selected: {selected_name}\n")
                return selected_course
            else:
                print(f"[-] Please enter a number between 1 and {len(courses)}")
        except ValueError:
            print("[-] Invalid input")

def crawl_and_download():
    """Main function: interactive crawler for selected course"""
    print("[*] Interactive munotes.in backup crawler")
    print(f"[*] Download directory: {DOWNLOAD_DIR}\n")
    
    # Get course selection
    selected_course = list_courses_interactive()
    if not selected_course:
        print("[!] Aborted by user")
        return
    
    course_name = selected_course.rstrip('/').split('/')[-1]
    total_downloads = 0
    total_found = 0
    
    print(f"[*] Fetching {course_name}...")
    
    # Get ALL semesters for selected course (no limit)
    semesters = get_semesters(selected_course)
    
    if len(semesters) == 0:
        print("[-] No semesters found for this course!")
        return
    
    print(f"[+] Found {len(semesters)} semesters for {course_name}\n")
    
    start_time = time.time()
    
    # Process ALL semesters (remove limit)
    for sem_idx, sem_url in enumerate(semesters, 1):
        sem_name = sem_url.rstrip('/').split('/')[-1]
        print(f"[{sem_idx}/{len(semesters)}] Semester: {sem_name}")
        
        # Get ALL years (no limit)
        years = get_years(sem_url)
        print(f"    └─ Found {len(years)} year folders")
        
        for year_url in years:
            year_name = year_url.rstrip('/').split('/')[-1]
            
            # Get ALL PDFs (no limit)
            pdf_urls = get_pdfs_for_year(year_url)
            
            if pdf_urls:
                total_found += len(pdf_urls)
                print(f"    ├─ {year_name}: {len(pdf_urls)} PDFs")
                
                # Download ALL PDFs (no limit)
                for pdf_idx, pdf_url in enumerate(pdf_urls, 1):
                    pdf_filename = os.path.basename(pdf_url).split('?')[0] or "document.pdf"
                    save_dir = os.path.join(DOWNLOAD_DIR, course_name, sem_name, year_name)
                    save_path = os.path.join(save_dir, pdf_filename)
                    
                    if not os.path.exists(save_path):
                        print(f"    │  [{pdf_idx}/{len(pdf_urls)}] Downloading: {pdf_filename[:50]}...")
                        if download_pdf(pdf_url, save_path):
                            total_downloads += 1
                    else:
                        print(f"    │  [→] {pdf_filename[:50]}... (exists)")
                
                time.sleep(0.3)  # Rate limiting
        
        print()
    
    elapsed = time.time() - start_time
    elapsed_min = int(elapsed // 60)
    elapsed_sec = int(elapsed % 60)
    
    print(f"\n{'='*70}")
    print(f"[+] BACKUP COMPLETE - {course_name}")
    print(f"{'='*70}")
    print(f"[*] Total PDFs found:     {total_found}")
    print(f"[*] Total PDFs downloaded: {total_downloads}")
    print(f"[*] Already existed:       {total_found - total_downloads}")
    print(f"[*] Time taken:           {elapsed_min}m {elapsed_sec}s")
    print(f"[*] Files saved to:       {DOWNLOAD_DIR}/{course_name}/")
    print(f"{'='*70}")

if __name__ == "__main__":
    try:
        crawl_and_download()
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user")
    except Exception as e:
        print(f"\n[!] Error: {e}")
