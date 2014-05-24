import json
import redis
import oauth2
import requests
import urllib

try:
    import config
except ImportError:
    print("Config file config.py.tmpl needs to be copied over to config.py")
    sys.exit(1)

class StashboardClient(object):

	def __init__(self):
		self.client = StashboardClient.build_client(config.CONSUMER_KEY, 
								config.CONSUMER_SECRET, 
								config.OAUTH_KEY,
								config.OAUTH_SECRET)
		self.base_admin_url = "%s/admin/api/v1" % config.BASE_URL


	def get_current_status(self, service):
		resp, content = self.client.request( self.base_admin_url + "/services/" + service + "/events/current", "GET")
		print resp['status']
		print content
		if resp['status'] != "200":
			if resp['status'] == '404':
				return 'Fail'
			raise Exception(content)
		last_event = json.loads(content)
		return last_event['status']['id']

	def post_event(self, status, service, message):
		if self.get_current_status(service) == status:
			return None
		if message is None:
			message = self.get_default_message(status)

		data = urllib.urlencode({
		    "status": status,
			"message": message
		})
		resp, content = self.client.request( self.base_admin_url + "/services/" + service + "/events", "POST", body=data)
		event = json.loads(content)
		if resp['status'] != '200':
			raise Exception(event['message'])
		return event

	@staticmethod	
	def build_client(consumer_key, consumer_secret, oauth_key, oauth_secret):
		consumer = oauth2.Consumer(key=consumer_key, secret=consumer_secret)
		token = oauth2.Token(oauth_key, oauth_secret)
		return oauth2.Client(consumer, token=token)


class ServiceStatus(object):
	def get_service(self):
		return None

	def status(self):
		return None


class DockerServiceStatus(ServiceStatus):
	def get_service(self):
		return "website"

	def status(self):
		r = requests.get('%s/srv/status' % config.DISCOURSE_URL)
		return {"ok": (True if r.text == 'ok' else False),
			"extra": r.status_code}


class SidekiqServiceStatus(ServiceStatus):
	def __init__(self):
		self.r_server = redis.Redis("localhost")

	def get_service(self):
		return "sidekiq"

	def status(self):
		sidekiq_jobs = {"EnsureDbConsistency": None,
				"Weekly": None,
				"EnqueueDigestEmails": None,
				"DashboardStats": None,
				"VersionCheck": None,
				"Heartbeat": None,
				"DestroyOldDeletionStubs": None,
				"CategoryStats": None,
				"DetectAvatars": None,
				"CreateBackup": None,
				"PollMailbox": None,
				"PendingUsersReminder": None,
				"PollFeed": None,
				"CleanUpUploads": None,
				"PeriodicalUpdates": None,
				"PurgeDeletedUploads": None,
				"PendingFlagsReminder": None}

		status = True
		for sidekiq_job in sidekiq_jobs:
			job_name = 'default:_scheduler_Jobs::%s' % sidekiq_job
			status_json = self.r_server.get(job_name)
			status_obj = json.loads(status_json)
			status_txt = status_obj['prev_result']
			sidekiq_jobs[sidekiq_job] = status_txt
			if status_txt != 'OK':
				status = False				

		extra_json = json.dumps(sidekiq_jobs)
		return {"ok": status,
			"extra": extra_json}

def main():
	sidekiq_status = SidekiqServiceStatus()
	jobs_status = sidekiq_status.status()
	print jobs_status

	docker_service_status = DockerServiceStatus()
	docker_status = docker_service_status.status()
	print docker_status

	client = StashboardClient()
	client.post_event(("up" if jobs_status['ok'] else "down"),
				"sidekiq",
				jobs_status['extra'])

	client.post_event(("up" if docker_status['ok'] else "down"),
				"website",
				docker_status['extra'])

if __name__ == '__main__':
	main()

