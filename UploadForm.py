import logging
from utils import *
from urllib.parse import urljoin,urlparse

class UploadForm :
	def __init__(self,notRegex,trueRegex,session,size,postData,uploadsFolder=None) :
		self.logger = logging.getLogger("fuxploider")
		self.postData = postData
		#self.uploadUrl = uploadUrl
		#self.formUrl = formUrl
		self.session = session
		self.trueRegex = trueRegex
		self.notRegex = notRegex
		#self.inputName = inputName
		self.uploadsFolder = uploadsFolder
		self.size = size
		self.validExtensions = []
		#self.httpRequests = 0
	#searches for a valid html form containing an input file, sets object parameters correctly
	def setup(self,initUrl) :
		self.formUrl = initUrl
		url = urlparse(self.formUrl)
		self.schema = url.scheme
		self.host = url.netloc

		self.httpRequests = 0
		try :
			initGet = self.session.get(self.formUrl,headers={"Accept-Encoding":None})
			self.httpRequests += 1
			if self.logger.verbosity > 1 :
				printSimpleResponseObject(initGet)
			if self.logger.verbosity > 2 :
				print("\033[36m"+initGet.text+"\033[m")
			if initGet.status_code < 200 or initGet.status_code > 300 :
				self.logger.critical("Server responded with following status : %s - %s",initGet.status_code,initGet.reason)
				exit()
		except Exception as e :
				self.logger.critical("%s : Host unreachable (%s)",getHost(initUrl),e)
				exit()
		#récupérer le formulaire,le détecter
		detectedForms = detectForms(initGet.text)
		if len(detectedForms) == 0 :
			self.logger.critical("No HTML form found here")
			exit()
		if len(detectedForms) > 1 :
			self.logger.critical("%s forms found containing file upload inputs, no way to choose which one to test.",len(detectedForms))
			exit()
		if len(detectedForms[0][1]) > 1 :
			self.logger.critical("%s file inputs found inside the same form, no way to choose which one to test.",len(detectedForms[0]))
			exit()

		self.inputName = detectedForms[0][1][0]["name"]
		self.logger.debug("Found the following file upload input : %s",self.inputName)
		formDestination = detectedForms[0][0]

		try :
			self.action = formDestination["action"]
		except :
			self.action = ""
		self.uploadUrl = urljoin(self.formUrl,self.action)

		self.logger.debug("Using following URL for file upload : %s",self.uploadUrl)

	#tries to upload a file through the file upload form
	def uploadFile(self,suffix,mime,payload) :
		with tempfile.NamedTemporaryFile(suffix=suffix) as fd :
			fd.write(payload)
			fd.flush()
			fd.seek(0)
			filename = os.path.basename(fd.name)
			self.logger.debug("Sending file %s with mime type : %s",filename,mime)
			fu = self.session.post(self.uploadUrl,files={self.inputName:(filename,fd,mime)},data=self.postData)
			self.httpRequests += 1
			if self.logger.verbosity > 1 :
				printSimpleResponseObject(fu)
			if self.logger.verbosity > 2 :
				print("\033[36m"+fu.text+"\033[m")
		return (fu,filename)

	#detects if a given html code represents an upload success or not
	def isASuccessfulUpload(self,html) :
		result = False
		validExt = False
		if self.notRegex :
			fileUploaded = re.search(self.notRegex,html)
			if fileUploaded == None :
				result = True
				if self.trueRegex :
					moreInfo = re.search(self.trueRegex,html)
					if moreInfo :
						result = str(moreInfo.groups())
		if self.trueRegex and not result :
			fileUploaded = re.search(self.trueRegex,html)
			if fileUploaded :
				result = str(fileUploaded.groups())
		return result

	#detects valid extensions for this upload form (sending legit files with legit mime types)
	def detectValidExtensions(self,extensions,maxN,extList=None) :
		self.logger.info("### Starting detection of valid extensions ...")
		n = 0
		if extList :
			tmpExtList = []
			for e in extList :
				tmpExtList.append((e,getMime(extensions,e)))
		else :
			tmpExtList = extensions
		validExtensions = []
		for ext in tmpExtList :
			validExt = False
			if n < maxN :
				#ext = (ext,mime)
				n += 1
				fu = self.uploadFile("."+ext[0],ext[1],os.urandom(self.size))
				res = self.isASuccessfulUpload(fu[0].text)
				if res :
					self.validExtensions.append(ext[0])
					self.logger.info("\033[1m\033[42mExtension %s seems valid for this form.\033[m", ext[0])
					if res != True :
						self.logger.info("\033[1;32mTrue regex matched the following information : %s\033[m",res)
			else :
				break
		return n

	#detects if code execution is gained, given an url to request and a regex supposed to match the executed code output
	def detectCodeExec(self,url,regex) :
		if self.logger.verbosity > 0 :
			self.logger.debug("Requesting %s ...",url)
		r = self.session.get(url)
		if r.status_code >= 400 :
			self.logger.warning("Code exec detection returned an http code of %s.",r.status_code)
		self.httpRequests += 1
		if self.logger.verbosity > 1 :
			printSimpleResponseObject(r)
		if self.logger.verbosity > 2 :
			print("\033[36m"+r.text+"\033[m")
		res = re.search(regex,r.text)
		if res :
			return True
		else :
			return False

	#core function : generates a temporary file using a suffixed name, a mime type and content, uploads the temp file on the server and eventually try to detect
	#	if code execution is gained through the uploaded file
	def submitTestCase(self,suffix,mime,payload=None,codeExecRegex=None) :
		fu = self.uploadFile(suffix,mime,payload)
		uploadRes = self.isASuccessfulUpload(fu[0].text)
		result = {"uploaded":False,"codeExec":False}
		if uploadRes :
			result["uploaded"] = True
			self.logger.info("\033[1;32mUpload of '%s' with mime type %s successful\033[m",fu[1], mime)
			if uploadRes != True :
				self.logger.info("\033[1;32mTrue regex matched the following information : %s\033[m",uploadRes)
			if codeExecRegex and valid_regex(codeExecRegex) and (self.uploadsFolder or self.trueRegex) :
				if self.uploadsFolder :
					url = self.schema+"://"+self.host+"/"+self.uploadsFolder+"/"+fu[1]
					executedCode = self.detectCodeExec(url,codeExecRegex)
					if executedCode :
						result["codeExec"] = True
				#needs to be able to detect code execution through true-regex, maybe asking user for input
				#ex : true-regex detects "../../uploads/uploadedFile.php" : ask for preffix !
				else :
					self.logger.warning("Impossible to determine where to find the uploaded payload.")
		return result

	#detects html forms and returns a list of beautifulSoup objects (detected forms)
	def detectForms(html) :
		soup = BeautifulSoup(html,'html.parser')
		detectedForms = soup.find_all("form")
		returnForms = []
		if len(detectedForms) > 0 :
			for f in detectedForms :
				fileInputs = f.findChildren("input",{"type":"file"})
				if len(fileInputs) > 0 :
					returnForms.append((f,fileInputs))

		return returnForms