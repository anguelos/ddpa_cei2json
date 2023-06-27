# ddpa_cei2json
Trivial app trying to crudelly extract abstracts, tenors, dates from cei files.

# Offline mode:
```bash
./apps/ddpa_cei2json/bin/ddp_cei2json_compute -charter_paths ./misc/1000_CVCharters/*/*/*
```

Extracts fundamental data from cei files and stores them in "charter.cei2json.json".
Specifically 

# Online mode:

Run Static FSDB:
Run Static FSDB (this is so that links to charters will work):
```bash
./bin/ddp_serve_fsdb -root ./misc/1000_CVCharters/
```

```bash
./apps/ddpa_cei2json/bin/ddp_cei2json_serve -root ./misc/1000_CVCharters/
```

Provides a demo web service with trivial word search over Tenors, Abstracts or both.
And a reverse index from every word occuring in the corpus to the actual abstract or tenor in context.
The service in it's HTML format, also links to the default charter presentation service (Static FSDB).