from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import pandas as pd
from datetime import date, timedelta

OUTPUT_CSV = "ontario_court_lists_tomorrow.csv"

def run(municipality="All", court_type="All"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        # 1) Open Tomorrow landing and accept T&Cs
        page.goto("https://www.ontariocourtdates.ca/tomorrow/", wait_until="domcontentloaded")
        try:
            # The consent is usually a button with visible text "I Agree"
            page.get_by_role("button", name="I Agree", exact=True).click(timeout=3000)
        except PlaywrightTimeoutError:
            # Some builds render the consent as an input or link; try a few fallbacks:
            for sel in [
                "text=I Agree",
                "input[type=submit][value='I Agree']",
                "button:has-text('I Agree')",
                "a:has-text('I Agree')",
            ]:
                try:
                    page.locator(sel).first.click(timeout=1500)
                    break
                except PlaywrightTimeoutError:
                    pass

        # 2) Go to the docket selection page (link appears in sitemap/nav)
        # If the link is present, click it; otherwise, navigate directly.
        try:
            page.get_by_role("link", name="Daily Dockets Selection", exact=False).click(timeout=3000)
        except PlaywrightTimeoutError:
            # Direct path; site sometimes routes this to the selection form after consent
            page.goto("https://www.ontariocourtdates.ca/daily-docket.aspx", wait_until="domcontentloaded")

        # 3) Fill selections
        # The page typically has dropdowns for Municipality and Court (SCJ/OCJ/All),
        # and radio or date controls for Today/Tomorrow.
        # Use robust label-based selection first; fall back to name/id if needed.
        # (Adjust selectors if your local inspection shows different labels.)
        def select_option_by_label(label_text, option_text):
            dd = page.get_by_label(label_text)
            try:
                dd.select_option(label=option_text)
            except:
                # Some dropdowns require clicking and selecting by text
                dd.click()
                page.get_by_role("option", name=option_text).click()

        # Choose Tomorrow if there is an explicit toggle
        for possible in ["Tomorrow", "View tomorrow", "Tomorrow’s court lists"]:
            try:
                page.get_by_label(possible).check(timeout=1000)
                break
            except:
                try:
                    page.get_by_role("radio", name=possible, exact=False).check(timeout=1000)
                    break
                except:
                    pass

        # Municipality
        try:
            select_option_by_label("Municipality", municipality)
        except:
            # common fallback ids/names
            for sel in ["#ddlMunicipality", "select[name='Municipality']", "select:has(option:has-text('All'))"]:
                try:
                    page.select_option(sel, label=municipality)
                    break
                except:
                    pass

        # Court type (All / Superior Court of Justice / Ontario Court of Justice)
        try:
            select_option_by_label("Court", court_type)
        except:
            for sel in ["#ddlCourt", "select[name='Court']"]:
                try:
                    page.select_option(sel, label=court_type)
                    break
                except:
                    pass

        # Submit search
        for sel in [
            "button:has-text('Search')",
            "input[type=submit][value='Search']",
            "button:has-text('View')",
        ]:
            try:
                page.locator(sel).first.click(timeout=3000)
                break
            except:
                pass

        page.wait_for_load_state("domcontentloaded")

        # 4) Expand accordions/sections if present so all rows are in the DOM
        # Many results are grouped by courthouse/room; expand “Show/Expand all” when available.
        for sel in [
            "button:has-text('Expand All')",
            "a:has-text('Expand All')",
            "button:has-text('Show All')",
        ]:
            if page.locator(sel).first.count():
                page.locator(sel).first.click()

        # 5) Scrape tables/rows
        # The columns (per FAQ) generally include: case/party name(s), case number,
        # time, location/room, appearance type/reason, method of attendance, and (for OCJ criminal) Docket Line.
        rows_data = []

        # Primary attempt: any result table rows (skip header)
        tables = page.locator("table").all()
        for t in tables:
            headers = [h.inner_text().strip() for h in t.locator("thead th, thead td").all()] or \
                      [h.inner_text().strip() for h in t.locator("tr").first.locator("th").all()]
            # map header names to indices
            body_rows = t.locator("tbody tr")
            for r in range(body_rows.count()):
                cells = body_rows.nth(r).locator("td").all()
                if not cells:
                    continue
                values = [c.inner_text().strip() for c in cells]
                row = {}
                if headers and len(headers) == len(values):
                    for h, v in zip(headers, values):
                        row[h] = v
                else:
                    # Fallback: positional fields
                    row = {
                        "col_1": values[0] if len(values) > 0 else "",
                        "col_2": values[1] if len(values) > 1 else "",
                        "col_3": values[2] if len(values) > 2 else "",
                        "col_4": values[3] if len(values) > 3 else "",
                        "col_5": values[4] if len(values) > 4 else "",
                        "col_6": values[5] if len(values) > 5 else "",
                        "col_7": values[6] if len(values) > 6 else "",
                        "col_8": values[7] if len(values) > 7 else "",
                    }
                rows_data.append(row)

        # 6) Save CSV
        if rows_data:
            df = pd.DataFrame(rows_data)
            # Add metadata to help downstream use
            df.insert(0, "scrape_date", date.today().isoformat())
            df.insert(1, "target_day", (date.today() + timedelta(days=1)).isoformat())
            df.to_csv(OUTPUT_CSV, index=False)
            print(f"Saved {len(df)} rows to {OUTPUT_CSV}")
        else:
            print("No rows found. You may need to adjust selectors or municipality/court filters.")

        ctx.close()
        browser.close()

if __name__ == "__main__":
    # Examples:
    # run(municipality="All", court_type="All")
    # run(municipality="Toronto", court_type="Superior Court of Justice")
    run()
