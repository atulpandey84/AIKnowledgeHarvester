# Mitigated API authentication bypass for python.org download metadata

**Source:** [https://blog.python.org/2026/06/mitigated-api-bypass-for-download-metadata-python-dot-org/](https://blog.python.org/2026/06/mitigated-api-bypass-for-download-metadata-python-dot-org/)
**Topic:** Google Cloud AI
**Publisher:** blog.python.org
**Published Date:** 2026-06-23
**Harvest Date:** 2026-07-10 11:30:53
**Keywords:** sigstore, were, authentication, audit, report, urls, python, february, vulnerability, auditing

---

Mitigated API authentication bypass for python.org download metadata
Summary
On February 23rd 2026, Splitline Ng from the DEVCORE Research Team reported to the Python Security Response Team (PSRT) an authentication bypass vulnerability in the python.org release management API. By supplying an admin username with an arbitrary API key the request was processed with admin privileges.
If exploited, this would have allowed an attacker to modify Python release and file metadata that affects what URLs users are offered when visiting python.org/downloads. While it would not enable existing release files to be modified in-place, it would enable an attacker to modify the URLs that are provided on python.org for each release file, including verification material URLs. There is no evidence this vulnerability was exploited after auditing logs and database backups. This scenario is even more unlikely to have happened unnoticed due to the many redistributors requiring Python Sigstore and PGP materials be verified prior to builds.
Details
PSRT confirmed the vulnerability on a local instance of python.org. Seth Larson and Hugo van Kemenade developed and deployed the patch to production with help from Jacob Coffee. Less than 48 hours after the initial report the PSRT and the reporter confirmed that the proof-of-concept provided by the reporter no longer worked locally or on the production deployment.
This vulnerability was likely never exploited. However, due to the age of the vulnerability (existing in the codebase since 2014) we don’t have absolute certainty beyond our logs and database backups. We believe attempts to exploit this vulnerability would have been “loud” and discovered quickly given the number of downstream tools and distributions automatically verifying the Sigstore and PGP materials.
We confirmed that all artifacts on python.org had not been modified by verifying Sigstore and PGP materials. Our own workflow verifying all Sigstore signatures did not signal any changes to artifacts from years prior. While verifying PGP materials we were able to verify all signatures where keys are still readily accessible from Python 2.5 to 3.13. Note that Python 3.14 and onwards no longer provide PGP materials, so these were verified with Sigstore.
The codebase was manually audited and additional hardening was applied. In addition to manual auditing, LLM auditing tools were unable to find additional issues with authentication. The delay between the initial finding and publishing of this final report was to give ample time for auditing for other issues related to authentication, to receive access to LLM auditing tools, and to complete a third-party audit from Trail of Bits prior to publication of this report.
Remediations
- Patch applied and deployed to ensure that behavior is not mixed between the “guest” authentication mode and API key authentication. This fixes the issue and documents clearly the branch in behavior between the two cases (python/pythondotorg#2946). Trail of Bits audit improved this functionality to require HTTPS URLs for newer releases (python/pythondotorg#3014) through a custom field validator.
- Added test cases for all negative authentication branches.
- Database and API now reject URLs which do not start with “https://www.python.org/”. This additional hardening will reject attacker-controlled URLs even if authentication or authorization is circumvented. (python/pythondotorg#2947)
- Increased logging retention from 3 days to 30 days for requests to python.org. This will aid in audit work for any follow-up reports.
Timeline
- February 23rd: Report received from DEVCORE Research Team.
- February 23rd: Report acknowledged and confirmed by PSRT.
- February 24th: Patch reviewed and applied to python.org.
- February 24th: Patch confirmed working by DEVCORE Research Team.
- February 25th: Audit of logs, database backups, Sigstore and PGP completed, showing no exploitation. Codebase was manually audited by staff.
- April 23rd: LLM security auditing tools were applied to the codebase, finding no issues related to authentication or authorization.
- June 1st: Trail of Bits began audit of python.org and Python release process.
- June 23rd: This final report is published.
Acknowledgements
Thanks to Splitline Ng from the DEVCORE Research Team for responsibly disclosing this vulnerability and confirming the remediation.
Funding for the follow-up third-party audit was provided by OpenAI. The audit and mitigations were completed by Trail of Bits, with special thanks to Facundo Tuesca and Eric Quintero. Audit results and mitigations were reviewed and applied by Seth Larson. Seth Larson’s role as Security Developer-in-Residence at the Python Software Foundation is supported by Alpha-Omega.
If your organization wants to support security at the Python Software Foundation through the Developers-in-Residence program please reach out to sponsors@python.org.