#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
						print_function)

__license__   = 'GPL v3'
__copyright__ = '2015, Xtina Schelin <xtina.schelin@gmail.com>'
__docformat__ = 'restructuredtext en'

import time
from urllib import quote
from Queue import Queue, Empty
from collections import OrderedDict

from lxml.html import fromstring, tostring

from calibre import as_unicode
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.icu import lower
from calibre.utils.cleantext import clean_ascii_chars
from calibre.utils.localization import get_udc

class ISFDB(Source):
# http://manual.calibre-ebook.com/plugins.html#module-calibre.ebooks.metadata.sources.base
	name = 'ISFDB'
	description = _('Downloads metadata and covers from ISFDB')
	author = 'Xtina Schelin'
	version = (1, 0, 0)
	minimum_calibre_version = (0, 8, 0)

	capabilities = frozenset(['identify', 'cover'])
	touched_fields = frozenset(['title', 'authors', 'identifier:isfdb', 'identifier:isbn', 'publisher', 'pubdate', 'comments'])
	has_html_comments = False
	supports_gzip_transfer_encoding = False
	cached_cover_url_is_reliable = True

	BASE_URL = 'http://www.isfdb.org'
	SEARCH_URL = BASE_URL + '/cgi-bin/se.cgi?'

	def config_widget(self):
		'''
		Overriding the default configuration screen for our own custom configuration
		'''
		from calibre_plugins.isfdb.config import ConfigWidget
		return ConfigWidget(self)

	def get_book_url(self, identifiers):
		isfdb_id = identifiers.get('isfdb', None)
		if isfdb_id:
			url = '%s/cgi-bin/pl.cgi?%s' % (ISFDB.BASE_URL, isfdb_id)
			return ('isfdb', isfdb_id, url)

	def create_query(self, log, title=None, authors=None, identifiers={}):
		isbn = check_isbn(identifiers.get('isbn', None))
		if isbn is not None:
			return '%stype=ISBN&arg=%s' % (ISFDB.SEARCH_URL, isbn)
		tokens = []
		if title:
			title = title.replace('?', '')
			title_tokens = list(self.get_title_tokens(title, strip_joiners=False, strip_subtitle=True))
			if title_tokens:
				tokens += [quote(t.encode('utf-8') if isinstance(t, unicode) else t) for t in title_tokens]
		if authors:
			author_tokens = self.get_author_tokens(authors, only_first_author=True)
			if author_tokens:
				tokens += [quote(t.encode('utf-8') if isinstance(t, unicode) else t) for t in author_tokens]
		if len(tokens) == 0:
			return None
		return ISFDB.SEARCH_URL + 'arg=' + '+'.join(tokens)

	def get_cached_cover_url(self, identifiers):
		url = None
		isfdb_id = identifiers.get('isfdb', None)
		if isfdb_id is None:
			isbn = identifiers.get('isbn', None)
			if isbn is not None:
				isfdb_id = self.cached_isbn_to_identifier(isbn)
		if isfdb_id is not None:
			url = self.cached_identifier_to_cover_url(isfdb_id)
		return url

	def cached_identifier_to_cover_url(self, id_):
		with self.cache_lock:
			url = self._get_cached_identifier_to_cover_url(id_)
			if not url:
				# Try for a "small" image in the cache
				url = self._get_cached_identifier_to_cover_url('small/' + id_)
			return url

	def _get_cached_identifier_to_cover_url(self, id_):
		# This must only be called once we have the cache lock
		url = self._identifier_to_cover_url_cache.get(id_, None)
		if not url:
			# We could not get a url for this particular id.
			for key in self._identifier_to_cover_url_cache.keys():
				if key.startswith('key_prefix'):
					return self._identifier_to_cover_url_cache[key]
		return url

	def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        print("identify")
		'''
		Note this method will retry without identifiers automatically if no
		match is found with identifiers.
		'''
		matches = []
		# If we have an ISFDB id then we do not need to fire a "search".
		# Instead we will go straight to the URL for that book.
		isfdb_id = identifiers.get('isfdb', None)
		isbn = check_isbn(identifiers.get('isbn', None))
		br = self.browser
		if isfdb_id:
			matches.append('%s/cgi-bin/pl.cgi?%s' % (ISFDB.BASE_URL, isfdb_id))
		else:
			title = get_udc().decode(title)
			authors = authors or []
			authors = [get_udc().decode(a) for a in authors]
			query = self.create_query(log, title=title, authors=authors, identifiers=identifiers)
			if query is None:
				log.error('Insufficient metadata to construct query. Alas!')
				return
			isbn_match_failed = False
			try:
				log.info('Querying: %s' % query)
				response = br.open_novisit(query, timeout=timeout)
				if isbn:
					# Check whether we got redirected to a book page for ISBN searches.
					# If we did, will use the url.
					# If we didn't then treat it as no matches on ISFDB
					location = response.geturl()
					# If not an exact match on ISBN we can get a search results page back
					# XMS: This may be terribly different for ISFDB.
					# XMS: HOWEVER: 1563890933 returns multiple results!
					isbn_match_failed = location.find('/pl.cgi') < 0
					if response.read().decode('utf-8', errors='replace').find('found 0 matches') == -1 and not isbn_match_failed:
						log.info('ISBN match location: %r' % location)
						matches.append(location)
			except Exception as e:
				if isbn and callable(getattr(e, 'getcode', None)) and e.getcode() == 404:
					# We did a lookup by ISBN but did not find a match
					# We will fallback to doing a lookup by title author
					log.info('Failed to find match for ISBN: %s' % isbn)
				elif callable(getattr(e, 'getcode', None)) and e.getcode() == 404:
					log.error('No matches for identify query')
					return as_unicode(e)
				else:
					err = 'Failed to make identify query'
					log.exception(err)
					return as_unicode(e)

			# For successful ISBN-based searches we have already done everything we need to.
			# So anything from this point below is for title/author based searches.
			if not isbn or isbn_match_failed:
				try:
					raw = response.read().strip()
					raw = raw.decode('utf-8', errors='replace')
					if not raw:
						log.error('Failed to get raw result for query')
						return
					root = fromstring(clean_ascii_chars(raw))
				except:
					msg = 'Failed to parse ISFDB page for query'
					log.exception(msg)
					return msg
				# Now grab the matches from the search results, provided the
				# title and authors appear to be for the same book
				self._parse_search_results(log, title, authors, root, matches, timeout)

		if abort.is_set():
			return

		if not matches:
			if identifiers and title and authors:
				log.info('No matches found with identifiers, retrying using only title and authors')
				return self.identify(log, result_queue, abort, title=title, authors=authors, timeout=timeout)
			log.error('No matches found with query: %r' % query)
			return

		from calibre_plugins.isfdb.worker import Worker
		workers = [Worker(url, result_queue, br, log, i, self) for i, url in enumerate(matches)]

		for w in workers:
			w.start()
			# Don't send all requests at the same time
			time.sleep(0.1)

		while not abort.is_set():
			a_worker_is_alive = False
			for w in workers:
				w.join(0.2)
				if abort.is_set():
					break
				if w.is_alive():
					a_worker_is_alive = True
			if not a_worker_is_alive:
				break

		return None

	def _parse_search_results(self, log, orig_title, orig_authors, root, matches, timeout):
		results = root.xpath('//div[@id="main"]/table/tr')
		if not results:
			#log.info('FOUND NO RESULTS:')
			return

		def ismatch(title, authors):
			authors = lower(' '.join(authors))
			title = lower(title)
			match = not title_tokens
			for t in title_tokens:
				if lower(t) in title:
					match = True
					break
			amatch = not author_tokens
			for a in author_tokens:
				if lower(a) in authors:
					amatch = True
					break
			if not author_tokens: amatch = True
			return match and amatch

		import calibre_plugins.isfdb.config as cfg
		max_results = cfg.plugin_prefs[cfg.STORE_NAME][cfg.KEY_MAX_DOWNLOADS]
		title_url_map = OrderedDict()
		for result in results:
			#log.info('Looking at result:')
			title = ''.join(result.xpath('.//img[contains(@class, "product-image")]/@alt'))
			if not title:
				#log.info('Could not find title')
				continue
			# Strip off any series information from the title
			#log.info('FOUND TITLE:',title)
			if '(' in title:
				#log.info('Stripping off series(')
				title = title.rpartition('(')[0].strip()
			# Also strip off any NOOK Book stuff from the title
			title = title.replace('[NOOK Book]', '').strip()

			#contributors = result.xpath('.//ul[@class="contributors"]//li[position()>1]//a')
			contributors = result.xpath('.//a[@class="contributor"]')
			authors = []
			for c in contributors:
				author = c.text_content().split(',')[0]
				#log.info('Found author:',author)
				if author.strip():
					authors.append(author.strip())

			#log.info('Looking at tokens:',author)
			title_tokens = list(self.get_title_tokens(orig_title))
			author_tokens = list(self.get_author_tokens(orig_authors))
			log.info('Considering search result: %s %s' % (title, authors))
			if not ismatch(title, authors):
				log.error('Rejecting as not close enough match: %s %s' % (title, authors))
				continue

			# Validate that the format is one we are interested in
			format_details = result.xpath('.//span[@class="format"]/text()')
			valid_format = False
			for format in format_details:
				#log.info('**Found format: %s'%format)
				if format.lower() not in UNSUPPORTED_FORMATS:
					valid_format = True
					break
			result_url = None
			if valid_format:
				# Get the detailed url to query next
				result_url = ''.join(result.xpath('.//a[@class="title"]/@href'))
				#log.info('**Found href: %s'%result_url)

			if result_url and title not in title_url_map:
				title_url_map[title] = result_url
				if len(title_url_map) >= 5:
					break

		for title in title_url_map.keys():
			matches.append(title_url_map[title])
			if len(matches) >= max_results:
				break


	def download_cover(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
		cached_url = self.get_cached_cover_url(identifiers)
		if cached_url is None:
			log.info('No cached cover found, running identify')
			rq = Queue()
			self.identify(log, rq, abort, title=title, authors=authors,
					identifiers=identifiers)
			if abort.is_set():
				return
			results = []
			while True:
				try:
					results.append(rq.get_nowait())
				except Empty:
					break
			results.sort(key=self.identify_results_keygen(title=title, authors=authors, identifiers=identifiers))
			for mi in results:
				cached_url = self.get_cached_cover_url(mi.identifiers)
				if cached_url is not None:
					break
		if cached_url is None:
			log.info('No cover found')
			return

		if abort.is_set():
			return
		br = self.browser
		log('Downloading cover from:', cached_url)
		try:
			cdata = br.open_novisit(cached_url, timeout=timeout).read()
			result_queue.put((self, cdata))
		except:
			log.exception('Failed to download cover from:', cached_url)

if __name__ == '__main__': # tests
	# To run these test use:
	# calibre-debug -e __init__.py
	from calibre import prints
	from calibre.ebooks.metadata.sources.test import (test_identify_plugin, title_test, authors_test)

	def cover_test(cover_url):
		if cover_url is not None:
			cover_url = cover_url.lower()

		def test(mi):
			mc = mi.cover_url
			if mc is not None:
				mc = mc.lower()
			if mc == cover_url:
				return True
			prints('Cover test failed. Expected: \'%s\' found: ' % cover_url, mc)
			return False
		return test

	# Test the plugin.
	test_identify_plugin(ISFDB.name,
		[
			(# A book with an ISBN
				{'identifiers':{'isbn': '9780345470638'},
					'title':'Black House', 'authors':['Stephen King', 'Peter Straub']},
				[title_test('Black House', exact=True),
				 authors_test(['Stephen King', 'Peter Straub']),
				 cover_test('http://images.amazon.com/images/P/034547063X.01.LZZZZZZZ.jpg')]
			),

			(# A book with no ISBN specified
				{'title':'Black House', 'authors':['Stephen King', 'Peter Straub']},
				[title_test('Black House', exact=True),
				 authors_test(['Stephen King', 'Peter Straub']),
				 cover_test('http://images.amazon.com/images/P/034547063X.01.LZZZZZZZ.jpg')]
			),

			(# A book with an ISFDB ID
				{'identifiers':{'isfdb': '4638'},
					'title':'Black House', 'authors':['Stephen King', 'Peter Straub']},
				[title_test('Black House', exact=True),
				 authors_test(['Stephen King', 'Peter Straub']),
				 cover_test('http://images.amazon.com/images/P/034547063X.01.LZZZZZZZ.jpg')]
			)
		], fail_missing_meta=False)
