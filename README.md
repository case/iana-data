# iana-data

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
