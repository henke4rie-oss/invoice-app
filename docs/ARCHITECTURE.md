# Architecture

Target architecture for the business-grade version (branch `v3`). It covers the South African VAT invoicing core, tenancy, documents, the email pipeline, client import, keyboard-first UI and the platform. Implementation happens in phases, each reviewed before it is merged.

> Nothing here is legal or tax advice. The invoice template, VAT logic and legal text must be reviewed by a tax practitioner and a lawyer before the product is sold.

## Decisions
| Topic | Decision |
|---|---|
| Tax scope | **South Africa first**: SARS VAT Act s20/s21. Rates and rules are **data**, so other countries can be added later without a rewrite. |
| Database | **Postgres + Alembic migrations** (replaces SQLite). |
| Invoice output | **Server-generated PDF**, stored when the invoice is issued and never re-rendered. |
| Excel import | **Clients only**, `.xlsx` and `.csv`. |
| Email provider | **Resend** over HTTPS, behind an adapter. Render's free plan blocks SMTP. See the Email section |
| Sending domain | A dedicated `mail.` subdomain with SPF, DKIM and DMARC (see the email launch checklist) |
| Demo email | **Preview outbox** ("Sent emails" page). Nothing is ever sent |
| Frontend | **Plain ES modules** (no build step). Drop `'unsafe-inline'` from the CSP |

## Facts this design relies on (verify before launch; see "Launch gates")
- SA standard VAT rate is **15%** (unchanged since April 2018; the 15.5% and 16% proposals were withdrawn). The rate must still come from a dated `tax_rates` table, never a constant.
- **s20(4) full tax invoice** must show:
  - the words "Tax Invoice";
  - the supplier's name, address and VAT number;
  - the recipient's name, address and VAT number (if they are a vendor);
  - a serial number and the date of issue;
  - a full description of the goods or services, with quantity or volume;
  - the value of the supply, the VAT amount and the total consideration (or a VAT-inclusive total plus a statement that it includes VAT at 15%).
- **s20(5) abridged tax invoice** (consideration ≤ R5,000) may omit the recipient's details.
- Issue within **21 days** of supply.
- Corrections to issued invoices are made with **credit or debit notes (s21)**, never by editing.
- Records must be kept for **5 years** (Tax Administration Act s29).
- A business that is not VAT-registered must not show VAT or call the document a "Tax Invoice".
- 2026 brought a **voluntary** e-invoicing framework. It is not mandatory, so it is out of scope for now.
- Sources disagree on exact field counts. The tax-practitioner review checks the final template against the Act itself.

## Legal notes
1. **Terms printed on an invoice usually aren't binding by themselves.** They bind when the customer agreed to them beforehand (a quote, an order or a contract). So the product gives each business an editable **terms template**, which can be attached to quotes and contracts later. We don't promise that printing 20 clauses protects anyone.
2. **The app itself needs its own legal documents**, separate from what goes on invoices:
   - Terms of Service.
   - A POPIA-compliant Privacy Policy. Our customers' clients are data subjects, so we are an **operator** under POPIA and need operator terms.
   - A PAIA manual (check the exemptions).
   - A registered Information Officer.
3. **None of this is legal or tax advice.** Code ships with defaults clearly marked "draft – have a lawyer review". The launch gates below block charging money until a lawyer and a tax practitioner have signed off.

---

## Target architecture

### Backend modules (FastAPI, layered as today: routers → services → repositories)
```
app/
  core/        config, db (Postgres engine), security (tokens, rate limit), money (Decimal helpers)
  tenancy/     Business, Membership, get_current_business dependency  ← every query is scoped by business_id
  clients/     model, schemas, repo, service, router, import/ (xlsx/csv pipeline)
  tax/         tax_rates (dated), VAT rules (SA), invoice-type rules (full/abridged/non-VAT)
  invoicing/   invoices, invoice_lines, numbering, lifecycle (draft→issued→paid/credited), credit_notes, payments
  documents/   Jinja2 templates + WeasyPrint → PDF, storage (Postgres bytea + sha256), draft watermark
  reminders/   existing reminder logic, now driven by the outstanding balance
  search/      /api/search and /api/suggestions (pg_trgm indexes)
  audit/       append-only audit_log (issued, emailed, credited, imported, deleted)
  demo/        demo seeding (rebuilt on the new model: VAT invoices, lines, credit note, payment)
```

### Data model (Postgres; money in integer cents; quantities and rates as `NUMERIC`; never floats)
- **businesses**
  - Identity: owner_user_id, legal_name, trading_name, vat_registered (bool), vat_number (10 digits starting with 4, validated), company_reg_no.
  - Contact: physical_address (lines, city, postal_code, country), postal_address, email, phone, logo.
  - Banking: bank_name, account_holder, account_number, branch_code, account_type.
  - Invoice settings: default_payment_terms_days, invoice_prefix, credit_note_prefix, default_terms_template_id, currency (ZAR).
- **memberships** (user_id, business_id, role). **One login can own several businesses** (common in SA). The UI gets a business switcher. The active business is sent with each request (`X-Business-Id` header) and checked against memberships on every request; it is never trusted on its own. Each business has its own VAT number, numbering sequences, banking, logo and terms. Role: only "owner" for now; ready for staff and accountants later.
- **clients** (business_id)
  - Identity: legal_name, trading_name, contact_person, email, phone, vat_number, company_reg_no, is_vat_vendor.
  - Billing: billing address fields, payment_terms_days (override), notes.
  - Uniqueness per business: **VAT number only** (a partial unique index, enforced where it's set) and company_reg_no (the same). **Email is NOT unique**: one person can run several businesses and use the same email for all of them.
- **tax_rates**
  - Fields: country, code (`STD`, `ZERO`, `EXEMPT`), rate NUMERIC(6,4), valid_from, valid_to.
  - The rate is chosen by the **time of supply** date.
- **invoices** (business_id)
  - Header: client_id, status (`draft` | `issued` | `partially_paid` | `paid` | `credited` | `void`), doc_type (`tax_invoice` | `abridged_tax_invoice` | `invoice` for non-VAT businesses).
  - Number and dates: number (null until issued), issue_date, supply_date, due_date, currency.
  - Totals (computed, stored at issue): subtotal_excl_cents, vat_cents, total_incl_cents, amount_paid_cents, balance_cents.
  - Snapshots (JSON taken at issue, because the invoice must show the details as they were at that moment): supplier_snapshot, recipient_snapshot.
  - Terms: terms_snapshot (text). Notes: notes.
  - Document: pdf_document_id. Timestamps: created_at, issued_at.
- **invoice_lines**: position, description, quantity NUMERIC(14,3), unit_price_excl_cents, discount_pct, tax_code, line_excl_cents, line_vat_cents, line_incl_cents.
- **credit_notes**: same shape as invoices, plus original_invoice_id and reason. Numbered in their own sequence (`CN-0001`). Immutable, with their own PDF.
- **payments**: invoice_id, amount_cents, paid_on, method (EFT/card/cash), reference. Recording a payment updates the balance and status.
- **number_sequences**: business_id, kind (invoice/credit_note), next_value. The next number is taken under `SELECT … FOR UPDATE` in the issuing transaction, so there are **no gaps and no duplicates**, even under concurrency.
- **documents**: id, kind, bytes (bytea), sha256, created_at. Write-once.
- **terms_templates**: business_id, name, body (markdown-lite), is_default.
- **import_jobs**: business_id, file meta, parsed rows (JSONB), mapping, status, expires_at (1 h).
- **audit_log**: business_id, user_id, action, entity, entity_id, at, details JSON. Insert-only.
- Existing: users (keep the uat token binding), reminders (now reference the balance).

### Core rules (enforced in services, all unit-tested)
1. **Drafts are editable; issued documents are immutable.**
   - Issuing does the following in one transaction:
     - validates the invoice against the s20 rules;
     - takes the next number;
     - freezes the snapshots and totals;
     - renders and stores the PDF with its sha256;
     - writes an audit entry.
   - After that, the only allowed changes are payments, credit notes and void (a full credit note).
2. **Picking the document type when issuing:**
   - Business not VAT-registered → `invoice`, with no VAT columns and no "Tax Invoice" wording.
   - VAT-registered and total incl. VAT > R5,000 → full `tax_invoice`. Issuing is blocked if the recipient's name or address is missing, or if the recipient is a VAT vendor without a VAT number.
   - VAT-registered and total ≤ R5,000 → `abridged_tax_invoice` is allowed. The user can choose a full one instead.
3. **VAT maths:**
   - Use `Decimal` throughout.
   - Each line: VAT = round_half_up(line_excl × rate, 0.01).
   - Totals are the sums of the lines.
   - This rounding policy goes on the tax-practitioner checklist.
   - Zero-rated lines show 0% and are labelled. Exempt lines are listed separately.
4. **Foreign currency invoices** (USD and EUR exist today): allowed for exports, which are usually zero-rated. Whether the VAT must also be shown in ZAR (with an exchange rate) **goes to the tax practitioner**. Until then, issuing a non-ZAR invoice with standard-rated lines is blocked, with an explanation.
5. **Gap-free numbering** per business per kind. Numbers are assigned only at issue, so deleted drafts never create gaps.
6. **Account deletion vs the 5-year retention rule:** deletion now requires an **export first** (a zip of all PDFs plus CSVs). The UI explains that the user must keep VAT records for 5 years. The demo account is still excluded.

### Invoice layout (one Jinja2 template drives both the PDF and the on-screen preview)
- **Header:**
  - Left: logo, trading name, legal name, physical address, VAT number, registration number, contact details.
  - Right: a large document title (TAX INVOICE / INVOICE / CREDIT NOTE).
- **Meta block:** invoice number, issue date, supply date (if different), due date, reference/PO.
- **Bill to:** the client's legal name, address and VAT number.
- **Lines table:** # · description · qty · unit price excl. · VAT % · amount excl. Zebra rows, and the header row repeats on new pages.
- **Totals box** (right-aligned):
  - Subtotal excl. VAT
  - VAT @ 15%, plus a zero-rated subtotal if there is one
  - **Total incl. VAT**
  - Paid
  - **Balance due**
- **Payment panel:** banking details plus the line "Use invoice number as reference". Also the anti-fraud line "We will never change our banking details by email – call to confirm" (fake bank-detail emails are a common fraud in SA).
- **Terms:** the terms snapshot in small type.
- **Footer:** registration details · page X of Y.
- Paper: A4. Body font: Plus Jakarta Sans; numbers: JetBrains Mono. Embed the fonts in the Docker image, because WeasyPrint can't fetch Google Fonts at render time.
- Drafts carry a diagonal "DRAFT – NOT A TAX INVOICE" watermark.

### Default terms template (editable, marked "draft – lawyer review")
1. Payment terms: due within N days of the invoice date; the reference to use.
2. Late payment interest, at a rate the business sets, chargeable only where agreed. Point users to the lawyer note.
3. Retention of ownership of goods until paid in full (only for goods).
4. Disputes must be raised in writing within N days.
5. Banking-details fraud warning.
6. Prices in ZAR, including VAT where shown.
7. Collection costs, only where agreed.
8. Governing law: Republic of South Africa.
9. POPIA notice: how the client's personal information on the invoice is used.
10. Contact for queries.

The list from online can be loaded as optional clauses in the template editor. They are opt-in, not all printed by default.

### Excel/CSV client import (a pipeline that streams and uses bounded memory)
1. **Upload** `.xlsx` or `.csv` only. Reject `.xls`, `.xlsm` and macros.
   - Limits: ≤ 5 MB and ≤ 5,000 rows.
   - Zip-bomb guard for `.xlsx`: the total uncompressed size must be ≤ 50 MB, checked through `zipfile` before parsing.
   - `.xlsx` is parsed with `openpyxl` (`read_only=True, data_only=True`, so formulas are never evaluated). `.csv` is parsed with the csv module after sniffing the delimiter and encoding (utf-8-sig/cp1252).
2. **Mapping:** propose a column mapping from header synonyms (e.g. "Customer", "Client name", "E-mail", "VAT No", "Tel", "Address 1"). The user adjusts it in a wizard.
3. **Dry run:** validate each row. Check that a name is present, the email format, and the VAT number format (10 digits starting with 4). Find duplicates inside the file and against existing clients by **VAT number**, then company registration number. Email and name are **never** used to merge automatically, because one person can run several businesses. A row with no VAT or registration number that shares a name or email with an existing client is flagged **"possible duplicate"**, and the user decides per row (create new / update / skip). Return row-level errors.
4. **Commit:** one transaction. Duplicates are skipped or updated, as the user chooses. Return a summary, and write an audit entry.
5. **Error report:** a downloadable CSV with formula-injection escaping (prefix cells that start with `= + - @`). A sample template (`.xlsx` and `.csv`) is also downloadable.
6. **POPIA notice** in the wizard: "Only import contacts you have a lawful reason to process."

### Keyboard shortcuts and autocomplete
- **One shortcut registry** (key → action, label, scope). The same table drives the handlers, the `?` help overlay and the command palette.
  - Shortcuts never fire while typing in a field, except `Esc` and `Ctrl/⌘+Enter`.
  - Nothing overrides the browser's or a screen reader's own keys.
- **Bindings:**
  - `Ctrl/⌘+K`: command palette.
  - `?`: help.
  - `g d / g c / g i / g r / g s`: go to Dashboard / Clients / Invoices / Reminders / Settings.
  - `n i` / `n c`: new invoice / new client.
  - `/`: focus search.
  - `j / k` move between rows, `Enter` opens one, `e` edits.
  - `p`: PDF.
  - `Ctrl/⌘+Enter`: save the form.
  - `Esc`: close.
- **Command palette:** fuzzy search over actions, clients and invoices.
  - Searches the loaded data on the client side first, then falls back to `/api/search` (pg_trgm, limit 20, scoped by business).
- **Autocomplete:**
  - **Client combobox** in the invoice editor, following the ARIA 1.2 combobox pattern. Results show name, trading name and VAT number.
  - **Line-item suggestions** from the business's own history: `GET /api/suggestions/line-items?q=` returns the description and last unit price (pg_trgm index, limit 8).
  - The invoice number is a preview only; the real number is given at issue.
  - The due date comes from the client's terms, or the business default.
  - Typing VAT-inclusive prices is optional and gets converted.
  - The tax code defaults to the client's VAT status (e.g. zero-rated for exports).
- No third-party address-autocomplete APIs (privacy, and cost).

### Frontend architecture (plain ES modules, no build step)
The invoice editor, import wizard, command palette and combobox would push `index.html` past about 4,000 lines. The frontend uses **plain ES modules, served statically, with no build step**:
- Files: `index.html`, `css/app.css` and `js/{api,state,router,shortcuts,palette,combobox,invoice-editor,import-wizard,…}.js`.
- Bonus: we can then drop `'unsafe-inline'` from the CSP, which closes the XSS gap noted in v2.

### Platform
- **Postgres** everywhere: dev via `docker compose` (as PayrollZA does), tests in CI through a Postgres service container, prod on Neon (free) or Render Postgres (paid).
- **Alembic:** one baseline migration, then one migration per phase. Remove the `init_db` ALTER hacks.
- **Render:** a paid instance is needed before real customers (no sleep, no cold starts). Fix auto-deploy. Set `DATABASE_URL` and `TRUSTED_PROXY_HOPS`.
- **Dependencies:** `psycopg[binary]`, `alembic`, `openpyxl`, `jinja2`, `weasyprint` (plus Pango/cairo apt packages in the Dockerfile).

---

## Email

### Email inventory (everything the product sends)
| Who receives it | Email | Trigger | Attachment |
|---|---|---|---|
| Account owner | Verify your email | Register (resend button) | – |
| Account owner | Reset password / password changed | "Forgot password" / after a change | – |
| Account owner | Account deleted (export reminder) | Deletion | – |
| Account owner | Test email | Settings → Email → "Send test" | Sample PDF |
| Client | **Tax invoice** | "Send" on an issued invoice | Invoice PDF (stored at issue) |
| Client | **Credit note** | Issue plus send | Credit note PDF |
| Client | Payment receipt | Payment recorded (optional toggle) | – |
| Client | **Reminders** | Per-business schedule: −3 days (friendly), due day, +7, +14, +30 (firm). All configurable. They stop as soon as the invoice is paid or credited | Invoice PDF |

### Email architecture (module `backend/app/email/`)
1. **Outbox pattern.**
   - The business action and the email row are written in **the same DB transaction**. Nothing sends inside a request.
   - Table `email_messages`: business_id, user_id, kind, to/cc, reply_to, subject, html, text, attachment document ids, related entity (invoice / credit_note / reminder), **idempotency_key (unique)**, status (`queued | sending | sent | delivered | bounced | complained | failed | suppressed | preview`), attempts, next_attempt_at, last_error, provider_message_id, created_at, sent_at.
2. **Worker.** An APScheduler job runs every 15 s (it reuses `start_scheduler` in `backend/app/services/scheduler.py`):
   - It claims batches of 20 with `SELECT … FOR UPDATE SKIP LOCKED` (Postgres, from v3 Phase 1), so it's safe with more than one instance.
   - **Retries with backoff** (1 m, 5 m, 30 m, 2 h, 6 h; max 5 attempts) on network errors, 429 and 5xx.
   - Any other 4xx is a permanent failure.
   - It sends Resend's `Idempotency-Key`, so a retry never sends a second copy.
3. **Provider adapters** behind `EmailProvider.send(msg) -> ProviderResult`. Chosen with `EMAIL_PROVIDER`:
   - `resend`: HTTPS POST, attachments base64-encoded, API key from `RESEND_API_KEY`. Uses the HTTP client already in the deps (`httpx2`; confirm the import name), with a 10 s timeout.
   - `smtp`: for self-hosting, a paid plan, or local Mailpit. **Timeout 15 s**, STARTTLS.
   - `console`: development; logs the message.
   - `preview`: always used for the demo account. Stores the message with status `preview` and never makes a network call. This replaces `DemoSender`.
   - The master switch `ALLOW_OUTBOUND_EMAIL` is kept. When it's off, messages go to `preview`, so the user can still see them.
4. **Suppression list** (`email_suppressions`: email, reason, created_at). A hard bounce or spam complaint adds the address. Before sending, the worker skips suppressed addresses (status `suppressed`) and the UI explains why.
5. **Webhooks.** `POST /api/webhooks/email/resend`:
   - Verifies Resend's **Svix signature** (`svix-id` / `svix-timestamp` / `svix-signature`, `RESEND_WEBHOOK_SECRET`) and rejects timestamps older than 5 minutes.
   - Maps delivered / bounced / complained events onto messages and the suppression list.
   - Raw events go to `email_events`.
6. **Templates.**
   - Jinja2 **HTML (table layout, inline CSS, light theme**, because email clients render dark styling badly) plus a plain-text version for every email.
   - Branded per business: logo as an inline CID attachment, the business's colours and footer with VAT and registration numbers.
   - **From:** `"{Trading name} via InvoiceApp" <invoices@mail.{domain}>`. **Reply-To:** the business's own email, so client replies reach the business and not us.
   - Subject example: `Tax Invoice INV-0042 from Northwind Studio – R12,500.00 due 30 Nov`.
7. **Safety.**
   - Strip CR/LF from names and subjects (header injection).
   - Validate addresses with `email-validator`, which is already a dependency.
   - Generalise the per-user cap `MAX_REMINDERS_PER_DAY` (`reminder_service.py`) into a per-business daily email cap.
   - Keep the per-invoice-per-day dedupe; each reminder step's idempotency key is `invoice_id + step`.
   - Rate-limit password reset in its own bucket, reusing `rate_limit_bucket` in `backend/app/main.py`.
   - Reset and verify endpoints always return 200, so they can't be used to discover which emails have accounts.
8. **Account tokens.** Verify and reset tokens are random, **stored hashed**, single-use, and expire after 1 h (reset) or 24 h (verify). They are not JWTs, so they can be revoked.
   - Changing the password invalidates existing sessions. Do this by adding a `password_changed_at` check in `deps.get_current_user`, next to the existing `uat` check.

### Email UI
- **Invoice "Send" dialog:**
  - To and CC (pre-filled from the client).
  - Subject and message (pre-filled from the template, editable).
  - The PDF attachment shown as a chip.
  - A "Preview email" tab, rendered in a sandboxed `iframe srcdoc`.
- **Email history per invoice:** a timeline of queued → sent → delivered / bounced, plus retry info.
- **Settings → Email:**
  - Sender display name and reply-to.
  - Reminder schedule editor (steps, tone, on/off).
  - "Send test email to me".
  - A provider status line. The domain status is a checklist (SPF / DKIM / DMARC) once a domain exists.
- **Client page:** "Pause reminders" toggle, and a suppression warning if the client's address bounced.
- **Demo:** a **"Sent emails" outbox page** that lists previews with the rendered HTML and a PDF download. The banner says "In the demo, emails are previewed here, never sent."
- **Auth screens:** "Forgot password?", the reset form, and a "Verify your email" banner with a resend link.

## Launch gates (non-code)
1. A **tax practitioner** signs off the invoice and credit note PDFs, the rounding policy and the foreign-currency handling.
2. A **lawyer** reviews the default terms, Terms of Service, Privacy Policy/POPIA operator terms and the PAIA position.
3. **Information Officer** registered with the Information Regulator.
4. **Paid hosting**: paid Render instance, managed Postgres with backups, auto-deploy fixed.
5. **Email domain**: buy a `.co.za` domain and add `mail.` in Resend. Set up SPF, DKIM and DMARC. Set `RESEND_API_KEY` / `RESEND_WEBHOOK_SECRET` / `EMAIL_FROM_DOMAIN` / `ALLOW_OUTBOUND_EMAIL=true` in Render. Aim for mail-tester 9/10 or better.

### Email launch checklist
1. Buy a domain (for example `yourbrand.co.za`) and add the **subdomain** `mail.yourbrand.co.za` in Resend.
2. Add the DNS records Resend gives you: **SPF**, **DKIM** and **DMARC** (start with `p=none`, move to `quarantine` after 2 weeks of clean reports).
3. Set `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `EMAIL_FROM_DOMAIN` and `ALLOW_OUTBOUND_EMAIL=true` in Render. Register the webhook URL.
4. Test with mail-tester.com (aim for 9/10 or better), plus Gmail and Outlook inbox placement.
5. Until the domain exists, use Resend's test sender: it can email **only your own address**, which is enough for showing it off.

## Later roadmap (out of scope for v3)
Quotes → invoices (where terms become binding) · recurring invoices · online payments (PayFast/Yoco/Ozow) · team members and accountant access · e-invoicing (once SARS's voluntary framework matures) · multi-country tax packs.
