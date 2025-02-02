import frappe, base64
# from frappe.utils.pdf import get_pdf,cleanup
from frappe import _
from frappe.utils import get_url

@frappe.whitelist()
def print_silently(doctype, name, print_format, print_type):
	user = frappe.db.get_single_value("Silent Print Settings", "print_user")
	tab_id = frappe.db.get_single_value("Silent Print Settings", "tab_id")
	pdf = create_pdf(doctype, name, print_format)
	data = {"doctype": doctype, "name": name, "print_format": print_format, "print_type": pdf["print_type"], "tab_id": tab_id, "pdf": pdf["pdf_base64"]}
	frappe.publish_realtime("print-silently", data, user=user)

@frappe.whitelist()
def set_master_tab(tab_id):
	query = 'update tabSingles set value={} where doctype="Silent Print Settings" and field="tab_id";'.format(tab_id)
	frappe.db.sql(query)
	frappe.publish_realtime("update_master_tab", {"tab_id": tab_id})

@frappe.whitelist()
def create_pdf(doctype, name, silent_print_format, doc=None, no_letterhead=0):
	site_url = get_url()

	html = frappe.get_print(doctype, name, silent_print_format, doc=doc, no_letterhead=no_letterhead)
	html_as_pdf = frappe.get_print(doctype, name, silent_print_format, doc=doc, no_letterhead=no_letterhead, as_pdf=True)
	
	html_copy = html
	
	html = html.replace('href="/', f'href="{site_url}/')
	html = html.replace('src="/', f'src="{site_url}/')

	if not frappe.db.exists("Silent Print Format", silent_print_format):
		return
	silent_print_format = frappe.get_doc("Silent Print Format", silent_print_format)
	options = get_pdf_options(silent_print_format)
	old_options = options.copy()
	pdf, html_options = get_pdf(html, options=options)
	pdf_base64 = base64.b64encode(pdf)
	return {
		"pdf_base64": pdf_base64.decode(),
		"print_type": silent_print_format.default_print_type,
		"options": options,
		"old_options": old_options,
		"html_copy": html_copy,
		"html_options": html_options,
	}

def get_pdf_options(silent_print_format):	
	options = {
		"page-size": silent_print_format.get("page_size") or "A4",
		"margin-left": "0mm",
        "margin-right": "0mm",
        "margin-top": "0mm",
        "margin-bottom": "0mm",
	}
	if silent_print_format.get("page_size") == "Custom":
		options = {
			"page-width": silent_print_format.get("custom_width"),
			"page-height": silent_print_format.get("custom_height"),
			"margin-left": "0mm",
			"margin-right": "0mm",
			"margin-top": "0mm",
			"margin-bottom": "0mm",
		}
	return options


from distutils.version import LooseVersion
import pdfkit
import six
import io
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader, PdfWriter
from frappe.utils import scrub_urls
from frappe.utils.pdf import get_file_data_from_writer, read_options_from_html, get_wkhtmltopdf_version

PDF_CONTENT_ERRORS = ["ContentNotFoundError", "ContentOperationNotPermittedError",
	"UnknownContentError", "RemoteHostClosedError"]

def get_pdf(html, options=None, output=None):
	html = scrub_urls(html)
	html, options, html_options = prepare_options(html, options)

	options.update({
		"enable-local-file-access": "",       # Allow local file access
		"disable-smart-shrinking": "",       # Prevent scaling issues
		"javascript-delay": "2000",          # Wait for JavaScript to render
		"no-stop-slow-scripts": "",          # Prevent script timeouts
		"debug-javascript": "",
		"margin-left": "0mm",
		"margin-right": "0mm",
		"margin-top": "0mm",
		"margin-bottom": "0mm",
	})

	# options.update({
	# 	"disable-javascript": "",
	# 	"disable-local-file-access": ""
	# })

	filedata = ''
	if LooseVersion(get_wkhtmltopdf_version()) > LooseVersion('0.12.3'):
		options.update({"disable-smart-shrinking": ""})

	try:
		# Set filename property to false, so no file is actually created
		filedata = pdfkit.from_string(html, False, options=options or {})

		# https://pythonhosted.org/PyPDF2/PdfFileReader.html
		# create in-memory binary streams from filedata and create a PdfFileReader object
		reader = PdfReader(io.BytesIO(filedata))
	except OSError as e:
		if any([error in str(e) for error in PDF_CONTENT_ERRORS]):
			if not filedata:
				frappe.throw(_("PDF generation failed because of broken image links"))

			# allow pdfs with missing images if file got created
			if output:  # output is a PdfFileWriter object
				output.append_pages_from_reader(reader)
		else:
			raise

	if "password" in options:
		password = options["password"]
		if six.PY2:
			password = frappe.safe_encode(password)

	if output:
		output.append_pages_from_reader(reader)
		return output

	writer = PdfWriter()
	writer.append_pages_from_reader(reader)

	if "password" in options:
		writer.encrypt(password)

	filedata = get_file_data_from_writer(writer)

	return filedata, html_options


def prepare_options(html, options):
	print("\n", options, "\n")
	if not options:
		options = {}

	options.update({
		'print-media-type': None,
		'background': None,
		'images': None,
		'quiet': None,
		# 'no-outline': None,
		'encoding': "UTF-8",
		#'load-error-handling': 'ignore'
	})

	if not options.get("margin-right"):
		options['margin-right'] = '15mm'

	if not options.get("margin-left"):
		options['margin-left'] = '15mm'

	html, html_options = read_options_from_html(html)
	options.update(html_options or {})

	# cookies
	if frappe.session and frappe.session.sid:
		options['cookie'] = [('sid', '{0}'.format(frappe.session.sid))]

	# page size
	# if not options.get("page-size"):
	# 	options['page-size'] = frappe.db.get_single_value("Print Settings", "pdf_page_size") or "A4"

	# options['margin-left'] = '50mm'


	return html, options, html_options
