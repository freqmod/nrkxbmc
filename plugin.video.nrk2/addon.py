#(c) 2012 Frederik M.J. Vestre GPLv3
from xbmcswift2 import Plugin
from xbmcswift2 import xbmc, xbmcgui
from xbmcswift2 import download_page
import urllib

from bs4 import BeautifulSoup as BS
from threading import Thread

PROXY_HOST_NAME = 'localhost' # !!!REMEMBER TO CHANGE THIS!!!
PROXY_PORT_NUMBER = 14234 # Maybe set this to 9000.
plugin = Plugin()


def load_html(url):
    return BS(download_page(url))

def full_url(url):
	return "http://tv.nrk.no" + url

def full_proxy_url(url):
	global PROXY_HOST_NAME, PROXY_PORT_NUMBER;
	if(url[0:4]=="http"):
		url = url[16:]
	return "http://%s:%s%s" % (PROXY_HOST_NAME, PROXY_PORT_NUMBER, url)
def displaylist(programlist):
	return [{
        'label': program.div.a.h3.contents[0],
        'path': full_proxy_url(program.div.a["href"]),
        'icon': program.div.img["src"],
        'thumbnail': program.div.img["src"],
        'is_playable': True,
    } for program in programlist]
    	#img: program.div.img["src"]
#    	if li.div.span.span:
    		#times played: re.search("\d+", unicode(program.div.span.span.contents)).group(0)


#From SVT play
def unikeyboard(default, message):
	keyboard = xbmc.Keyboard(default, message)
	keyboard.doModal()
	if (keyboard.isConfirmed()):
		return keyboard.getText()
	else:
		return None


@plugin.route('/')
def index():
    return [
        {'label': 'Recommended', 'path': plugin.url_for('recommended')},
        {'label': 'Popular last week', 'path': plugin.url_for('popular_week')},
        {'label': 'Popular last month', 'path': plugin.url_for('popular_month')},
        {'label': 'Recently Broadcasted', 'path': plugin.url_for('recent')},
        {'label': 'Search', 'path': plugin.url_for('search')},
    ]

@plugin.route('/recommended')
def recommended():
	data = load_html("http://tv.nrk.no")
	return displaylist(data.find(id="recommended-list").ul.find_all("li"))

@plugin.route('/popular/month')
def popular_month():
	data = load_html("http://tv.nrk.no/listobjects/mostpopular/Month")
	return displaylist(data.ul.find_all("li"))

@plugin.route('/popular/week')
def popular_week():
	data = load_html("http://tv.nrk.no/listobjects/mostpopular/Week")
	return displaylist(data.ul.find_all("li"))


@plugin.route('/recent')
def recent():
	data = load_html("http://tv.nrk.no/listobjects/recentlysent")
	return displaylist(data.ul.find_all("li"))

@plugin.route('/play/<url>/')
def play_video(url):
  	item =  {
        'label': "tmp",
        'path': url,
    }
	plugin.play_video(item)
	
@plugin.route('/search')
def search():
	searchString = unikeyboard("", "" )
	if searchString == "":
		xbmcgui.Dialog().ok( "Search", "s2" )
	elif searchString:
		dialogProgress = xbmcgui.DialogProgress()
		dialogProgress.create( "", "Searching" , searchString)
		#The XBMC onscreen keyboard outputs utf-8 and this need to be encoded to unicode
		encodedSearchString = urllib.quote_plus(searchString.decode("utf_8").encode("raw_unicode_escape"))
		data = load_html("http://tv.nrk.no/sok?filter=rettigheter&q=%s" %(encodedSearchString))
		return displaylist(data.find_all(id="searchResult")[0].find_all("ul")[1].find_all("li"))
	return


import time
import BaseHTTPServer

#Download data from nrk.no/pluzzdl:
#License: GPLv2 

import xml.etree.ElementTree as ET
import sys
import urllib2
import re
import struct
import binascii
from base64 import b64decode
import atexit

def parse_webpage(weburl):
	webpage_h = urllib2.urlopen(weburl)
	webpage = webpage_h.read()
	webpage_h.close()
	manifest_res = re.search(r'data-media=\"([^\"]+)\"', webpage)
	manifest_url =  manifest_res.group(1) + '?hdcore=2.7.6'
	return manifest_url

def parse_manifest(manifest_url):
	namespace = "{http://ns.adobe.com/f4m/1.0}"
	manifest_h = urllib2.urlopen(manifest_url)
	manifest_d = manifest_h.read()
	manifest_h.close()
	manifest_t = ET.fromstring(manifest_d)

	manifest_bootstrap = {}
	for bootstrap in manifest_t.getiterator(namespace + 'bootstrapInfo'):
		manifest_bootstrap[bootstrap.get("id")] = bootstrap.text
	
	manifest_media = []
	for media in manifest_t.getiterator(namespace + 'media'):
		manifest_media.append({'bitrate': media.get('bitrate'),
								'bootstrap': b64decode(manifest_bootstrap[media.get('bootstrapInfoId')]),
								'url': media.get('url'),
								'metadata': b64decode(media.find(namespace + 'metadata').text)
								})
	return {'id': manifest_t.find(namespace + 'id').text,
			'duration': float( manifest_t.find( "{http://ns.adobe.com/f4m/1.0}duration" ).text ),
			'media': manifest_media}

def get_fragment_url(server, manifest, media_id, fragment_idx):
	return ("%s%s/%sSeg1-Frag%d" % (server, manifest['id'][0:-2], manifest['media'][media_id]['url'], fragment_idx))

def write_bootstrap(manifest, media_id):
	with open('bootstrap', 'wb') as fh:
		fh.write(manifest['media'][media_id]['bootstrap'])

def find_start_of_video(fragID, fragData ):
	#from pluzzdl
	# Skip fragment header
	start = fragData.find( "mdat" ) + 4
	# For all fragment (except frag1)
	if( fragID > 1 ):
		# Skip 2 FLV tags
		for dummy in range( 2 ):
			tagLen, = struct.unpack_from( ">L", fragData, start ) # Read 32 bits (big endian)
			tagLen &= 0x00ffffff                                  # Take the last 24 bits
			start  += tagLen + 11 + 4                             # 11 = tag header len ; 4 = tag footer len
	return start

def get_and_cut_fragment(url, frag_id):
	fragment_h = urllib2.urlopen(url)
	fragment_d = fragment_h.read()
	fragment_h.close()
	return fragment_d[ find_start_of_video(frag_id, fragment_d) : ]

def writefrags(server, manifest, mediaid):
	with open('/tmp/frags', 'wb') as fh:
		fh.write( binascii.a2b_hex( "464c56010500000009000000001200010c00000000000000" ) )
		fh.write( manifest['media'][4]['metadata'] )
		fh.write( binascii.a2b_hex( "00000000" ) ) # pad to have correct block size
		for i in xrange(1, int(manifest['duration']/6)):
				fh.write(get_and_cut_fragment(get_fragment_url(server, manifest, mediaid, i), i))

def download_main():
	manifest_url = parse_webpage(sys.argv[1])
	server = re.search(r'http:\/\/([^\.]+).akamaihd.net/z', manifest_url).group(0)
	manifest = parse_manifest(manifest_url)
	writefrags(server, manifest, len(manifest['media'])-1)

NRK_PROXY_CACHE = {}
class NrkProxy(BaseHTTPServer.BaseHTTPRequestHandler):
	def do_HEAD(s):
		s.send_response(200)
		s.send_header("Content-type", "text/html")
		s.end_headers()
	def do_GET(s):
		global NRK_PROXY_CACHE
		try:
			"""Respond to a GET request."""
			print "GET: Headers:", s.headers
			url = "http://tv.nrk.no" + unicode(s.path)
			print "URL:", url
			manifest = None
			if url not in NRK_PROXY_CACHE:
				manifest_url = parse_webpage(url)
				server = re.search(r'http:\/\/([^\.]+).akamaihd.net/z', manifest_url).group(0)
				manifest = parse_manifest(manifest_url)
				NRK_PROXY_CACHE[manifest_url] = manifest
			else:
				manifest = NRK_PROXY_CACHE[manifest_url]
			first_frag = get_and_cut_fragment(get_fragment_url(server, manifest, len(manifest['media'])-1, 1), 1)
			ffl = len(first_frag)
			first_frag = None

			s.send_response(200)
			s.send_header("Content-type", "video/mp4")
			s.send_header("Content-Length", "-1")
			s.send_header("Accept-Range", "bytes")
			s.send_header("Transfer-Encoding", "chunked")
			s.end_headers()
			#writefrags(server, manifest, )
			head =  binascii.a2b_hex( "464c56010500000009000000001200010c00000000000000" ) + manifest['media'][4]['metadata'] + binascii.a2b_hex( "00000000" )  
			s.wfile.write(hex(len(head))[2:]+"\r\n")
			s.wfile.write(head+"\r\n")
			for i in xrange(1, int(manifest['duration']/5)):
					try:
						fragment = get_and_cut_fragment(get_fragment_url(server, manifest, len(manifest['media'])-1, i), i)
						s.wfile.write(hex(len(fragment))[2:]+"\r\n")
						s.wfile.write( fragment +"\r\n")
					except URLError:
						s.wfile.write("0\r\n\r\n")#finished
		except Exception as ex:
			print ex
#TODO: check if a proxy is allready running at the proxy port
try:
	server_class = BaseHTTPServer.HTTPServer
	httpd = server_class((PROXY_HOST_NAME, PROXY_PORT_NUMBER), NrkProxy)
	thread = Thread(target = httpd.serve_forever)
	thread.daemon = True
	thread.start()

	atexit.register(httpd.server_close)
except Exception as ex:
	print "Server allready running", ex
if __name__ == '__main__':
	plugin.run()