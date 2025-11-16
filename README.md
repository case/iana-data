# iana-data

## Overview

[IANA](https://www.iana.org/) publishes some raw, canonical data about the DNS and root zone TLDs. This project is an attempt to make the IANA data easier to explore and interpret.

Here are the data files we're working with:

- The ["All TLDs" txt file](https://data.iana.org/TLD/tlds-alpha-by-domain.txt)
- The [Root DB html file](https://www.iana.org/domains/root/db), which alas doesn't appear to be available in a friendlier format
- The [RDAP "bootstrap" file](https://data.iana.org/rdap/dns.json)

There are a few challenges (and helpful patterns) with these data files, for example:

For the "All TLDs" text file:

- All the TLDs in there are delegated, e.g. "currently in the DNS"
- It doesn't say which are `generic` (gTLDs) vs `country-code` (ccTLDs)
- There are `xn--` IDNs in the file; some are gTLDs, and some are ccTLDs
- All two-character ASCII TLDs are ccTLDs, but not all two-character IDNs are ccTLDs

For the "Root DB" html file:

- It lists more TLDs than the "All TLDs" file, because it also includes some `undelegated` TLDs. (These have a `TLD Manager` value of `Not assigned`.)
- It has more "types" than just `generic` and `country-code` - it also lists `sponsored`, `infrastructure`, and `generic-restricted` types
- It shows the Unicode IDN variants in the rendered html, and their ASCII variants in their `href` links to the per-TLD pages on the IANA website
- We can use the combination of `country-code` and IDN status, to determine which IDNs are ccTLDs vs. gTLDs

## Operation

- `make download` - Downloads all the IANA files, and respecting cache headers

## Local dev

- `make deps` - Installs the project dependencies

## Todo

**Later**

- [ ] Check other git repos, for TLDs TXT list change history
    - [some txt file history](https://github.com/ris-work/TLD-watch/commits/master/)
    - [Go project](https://github.com/jehiah/generic_tlds/commits/master/)
    - ZoneDB has some history

**Done**

- [x] Basic CLI
- [x] Download functionality + cache control headers
- [x] Tests and Fixture data
