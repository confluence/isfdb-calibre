#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
						print_function)

__license__   = 'GPL v3'
__copyright__ = '2015, Xtina Schelin <xtina.schelin@gmail.com>'
__docformat__ = 'restructuredtext en'

import socket, re, datetime
from collections import OrderedDict
from threading import Thread

from lxml.html import fromstring, tostring

from calibre.ebooks.metadata.book.base import Metadata
from calibre.library.comments import sanitize_comments_html
from calibre.utils.cleantext import clean_ascii_chars

import calibre_plugins.isfdb.config as cfg

class Worker(Thread): # Get details

	'''
	Get book details from ISFDB book page in a separate thread.
	'''

	def __init__(self, url, result_queue, browser, log, relevance, plugin, timeout=20):
        print("Ohai")
		Thread.__init__(self)
		self.daemon = True
		self.url, self.result_queue = url, result_queue
		self.log, self.timeout = log, timeout
		self.relevance, self.plugin = relevance, plugin
		self.browser = browser.clone_browser()
		self.cover_url = self.isfdb_id = self.isbn = None

	def run(self):
        print("Ohai")
		try:
			self.get_details()
		except:
			self.log.exception('get_details failed for url: %r'%self.url)

	def get_details(self):
		try:
            print('ISFDB url: %r'%self.url)
			self.log.info('ISFDB url: %r'%self.url)
			raw = self.browser.open_novisit(self.url, timeout=self.timeout).read().strip()
		except Exception as e:
			if callable(getattr(e, 'getcode', None)) and \
					e.getcode() == 404:
				self.log.error('URL malformed: %r'%self.url)
				return
			attr = getattr(e, 'args', [None])
			attr = attr if attr else [None]
			if isinstance(attr[0], socket.timeout):
				msg = 'ISFDB.org timed out. Try again later.'
				self.log.error(msg)
			else:
				msg = 'Failed to make details query: %r'%self.url
				self.log.exception(msg)
			return

		raw = raw.decode('utf-8', errors='replace')

		if '<title>404 - ' in raw:
			self.log.error('URL malformed: %r'%self.url)
			return

		try:
			root = fromstring(clean_ascii_chars(raw))
		except:
			msg = 'Failed to parse ISFDB details page: %r'%self.url
			self.log.exception(msg)
			return

		self.parse_details(root)

	def parse_details(self, root):
		try:
			isfdb_id = self.parse_isfdb_id(self.url)
		except:
            print('Error parsing ISFDB ID for url: %r'%self.url)
			self.log.exception('Error parsing ISFDB ID for url: %r'%self.url)
			isfdb_id = None

		try:
			(title) = self.parse_title(root)
		except:
			self.log.exception('Error parsing title for url: %r'%self.url)
			title = None

		try:
			authors = self.parse_authors(root)
		except:
			self.log.exception('Error parsing authors for url: %r'%self.url)
			authors = []

		if not title or not authors or not isfdb_id:
			self.log.error('Could not find title/authors/ISFDB ID for %r'%self.url)
			self.log.error('ISFDB: %r Title: %r Authors: %r' % (isfdb_id, title,
				authors))
			return

		mi = Metadata(title, authors)
		mi.set_identifier('isfdb', isfdb_id)
		self.isfdb_id = isfdb_id

		try:
			isbn = self.parse_isbn(root)
			if isbn:
				self.isbn = mi.isbn = isbn
		except:
			self.log.exception('Error parsing ISBN for url: %r'%self.url)

		try:
			mi.comments = self.parse_comments(root)
		except:
			self.log.exception('Error parsing comments for url: %r'%self.url)

		try:
			self.cover_url = self.parse_cover(root)
		except:
			self.log.exception('Error parsing cover for url: %r'%self.url)
		mi.has_cover = bool(self.cover_url)
		mi.cover_url = self.cover_url # This is purely so we can run a test for it!!!

		try:
			mi.publisher = self.parse_publisher(root)
		except:
			self.log.exception('Error parsing publisher for url: %r'%self.url)

		try:
			mi.pubdate = self.parse_published_date(root)
		except:
			self.log.exception('Error parsing published date for url: %r'%self.url)

		mi.source_relevance = self.relevance

		if self.isfdb_id:
			if self.isbn:
				self.plugin.cache_isbn_to_identifier(self.isbn, self.isfdb_id)

		self.plugin.clean_downloaded_metadata(mi)
		self.result_queue.put(mi)

	def parse_isfdb_id(self, url):
		return re.search('(\d+)$', url).groups(0)[0]

	def parse_title(self, root):
		detail_nodes = root.xpath('//div[@id="MetadataBox"]//td[@class="pubheader"]/ul/li')
		if detail_nodes:
			for detail_node in detail_nodes:
				if detail_node[0].child_nodes()[0].text_content().strip().startswith('Publication'):
					return detail_node[0].child_nodes()[1].tail.strip()

	def parse_authors(self, root):
		author_nodes = root.xpath('//div[@id="MetadataBox"]//td[@class="pubheader"]/ul/li')
		if author_nodes:
			authors = []
			for author_node in author_nodes:
				section = author_node[0].child_nodes()[0].text_content().strip()
				if section.startswith('Authors') or section.startswith('Editors'):
					# XMS: This part is terrible. I need to update the xpath and looping for the [a] tags.
					author = author_node[0].child_nodes()[1].text.strip()
					authors.append(author)
			return authors

	def parse_isbn(self, root):
		# XMS: May be a problem. Check XPATH, and what happens if there isn't an ISBN.
		detail_nodes = root.xpath('//div[@id="MetadataBox"]//td[@class="pubheader"]/ul/li')
		if detail_nodes:
			for detail_node in detail_nodes:
				if detail_node[0].child_nodes()[0].text_content().strip().startswith('ISBN'):
					# XMS: Put in a bit here to capture the ISBN-13.
					# XMS: Also a bit to error when there isn't one, but ISBN was found.
					return detail_node[0].child_nodes()[1].tail.strip()

	def parse_publisher(self, root):
		detail_nodes = root.xpath('//div[@id="MetadataBox"]//td[@class="pubheader"]/ul/li')
		if detail_nodes:
			for detail_node in detail_nodes:
				if detail_node[0].child_nodes()[0].text_content().strip().startswith('Publisher'):
					return detail_node[0].child_nodes()[1].tail.strip()

	def parse_published_date(self, root):
		detail_nodes = root.xpath('//div[@id="MetadataBox"]//td[@class="pubheader"]/ul/li')
		if detail_nodes:
			for detail_node in detail_nodes:
				if detail_node[0].text_content().strip().startswith('Year'):
					pub_date_text = detail_node[0].child_nodes()[1].tail.strip()
					return self._convert_date_text(pub_date_text)

	def _convert_date_text(self, date_text):
		# 2008-08-00
		year = int(date_text[0:4])
		month = int(date_text[5:7])
		if month == 0:
			month = 1
		day = int(date_text[8:10])
		if day == 0:
			day = 1
		from calibre.utils.date import utc_tz
		return datetime.datetime(year, month, day, tzinfo=utc_tz)

	def parse_comments(self, root):
		default_append_contents = cfg.DEFAULT_STORE_VALUES[cfg.KEY_APPEND_CONTENTS]
		append_contents = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.KEY_APPEND_CONTENTS, default_append_contents)
		comments = ''
		if append_contents:
			contents_node = root.xpath('//div[@id="ContentBox"]/ul')
			if contents_node:
				contents = tostring(contents_node[0], method='html')
				comments += contents
		if comments:
			return comments

	def parse_cover(self, root):
		# First check to make sure there's an image there at all.
		page_image_box = root.xpath('//div[@id="MetadataBox"]/table/tbody/tr[1]/td[1]//img')
		if page_image_box:
			page_url = page_image_box[0].strip()
			return page_url
