# isfdb-calibre
A [Calibre](http://calibre-ebook.com/) plugin for [ISFDB](http://isfdb.org/).

This is based on the Barnes & Noble plugin that Grant Drake created. Thanks!

## Test Cases

Some test URLs for testing various issues. URLs are chosen based on their testing criteria and nothing else. Don't read anything into it. (Har.)

Test | URL
---- | ---
contents | http://www.isfdb.org/cgi-bin/pl.cgi?263886
no contents | http://www.isfdb.org/cgi-bin/pl.cgi?4638
no ISBN | http://www.isfdb.org/cgi-bin/pl.cgi?263886
duplicate ISBN | http://www.isfdb.org/cgi-bin/se.cgi?type=ISBN&arg=1563890933
ISBN-10 first | http://www.isfdb.org/cgi-bin/pl.cgi?4638
ISBN-13 first | http://www.isfdb.org/cgi-bin/pl.cgi?475592
cover image | http://www.isfdb.org/cgi-bin/pl.cgi?4638
no cover image | http://www.isfdb.org/cgi-bin/pl.cgi?294061
one author | http://www.isfdb.org/cgi-bin/pl.cgi?150571
multiple authors | http://www.isfdb.org/cgi-bin/pl.cgi?4638
editor(s), not authors | http://www.isfdb.org/cgi-bin/pl.cgi?371803
no editors, just authors | http://www.isfdb.org/cgi-bin/pl.cgi?279535 (nothing to be done)
normal publication date | http://www.isfdb.org/cgi-bin/pl.cgi?369181
no publication day | http://www.isfdb.org/cgi-bin/pl.cgi?150571
no publication month or day | http://www.isfdb.org/cgi-bin/pl.cgi?268031
