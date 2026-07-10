# Python 3.12.13, 3.11.15 and 3.10.20 are now available!

**Source:** [https://blog.python.org/2026/03/python-31213-31115-31020/](https://blog.python.org/2026/03/python-31213-31115-31020/)
**Topic:** Linux Mint Security
**Publisher:** blog.python.org
**Published Date:** 2013-12-03
**Harvest Date:** 2026-07-10 11:30:54
**Keywords:** memory, releases, release, denial, python, related, fixed, http, security, email

---

Python 3.12.13, 3.11.15 and 3.10.20 are now available!
Python Releases For Your Security!
New security releases for 3.10, 3.11 and 3.12 are now available. (As these Python versions are now in security-fix-only mode, these are source-only releases, and there is no pre-set release cadence.)
Security content in these releases
Email and header-related
- gh-144125: email.generator.BytesGeneratornow refuses to serialize headers that are unsafely folded or delimited (seeemail.policy.Policy.verify_generated_headers); addressing CVE-2024-6923.
- gh-143935: Fixed comment folding in modern email policies to prevent header injection when very long non-foldable comment text is wrapped.
- gh-136063: email.messagenow ensures linear complexity for legacy HTTP parameter parsing.
HTTP, cookies, and URL parsing-related
- gh-143916: wsgiref.headers.Headersnow rejects C0 control characters in fields, values, and parameters.
- gh-143919: http.cookies.Morselnow rejects control characters in fields and values.
- gh-143925: data:URL media types now reject control characters.
XML-related
- gh-144363: Upgraded bundled libexpat to 2.7.4 to fix CVE-2026-24515 and CVE-2026-25210.
- gh-90949: Added Expat allocation-tracker APIs to xml.parsers.expatparser objects to limit memory amplification from malicious XML input; includes mitigation for CVE-2025-59375.
- gh-142145: Removed quadratic behavior in xml.dom.minidomnode ID cache clearing.
Denial-of-service hardening
- gh-119342: Fixed a potential memory denial of service in plistlib.
- gh-119451: Fixed a potential memory denial of service in http.client.
- gh-119452: Fixed a potential memory denial of service in http.server(CGI server on Windows).
- gh-136065: Fixed quadratic complexity in os.path.expandvars().
HTML parsing-related
- gh-137836: Hardened html.parser.HTMLParserwith support for additional RAWTEXT/PLAINTEXT elements (plaintext,xmp,iframe,noembed,noframes, optionalnoscript), improving robust handling of hostile markup.
SSL memory-safety fixes
- gh-144833: Fixed a use-after-free in sslwhenSSL_new()fails.
Python 3.12.13
python.org/downloads/release/python-31213
Python 3.11.15
Additional fixes in this release (they were already included in a previous 3.12 release):
- gh-120298: Fixed a use-after-free in list rich comparison handling (list_richcompare_impl) for specially crafted concurrent inputs.
- gh-120384: Fixed an out-of-bounds access in list slice assignment (list_ass_subscript) under specially crafted concurrent inputs.
python.org/downloads/release/python-31115
Python 3.10.20
Additional fixes in this release (they were already included in a previous 3.12 release):
- gh-120298: Fixed a use-after-free in list rich comparison handling (list_richcompare_impl) for specially crafted concurrent inputs.
- gh-120384: Fixed an out-of-bounds access in list slice assignment (list_ass_subscript) under specially crafted concurrent inputs.
python.org/downloads/release/python-31020
Stay safe and upgrade!
As always, upgrading is highly recommended to all users of affected versions.
Enjoy the new releases
Thanks to all of the many volunteers who help make Python Development and this release possible! Please consider supporting our efforts by volunteering yourself or through organisation contributions to the Python Software Foundation.
Regards from your security-fix release team, Thomas Wouters Pablo Galindo Salgado