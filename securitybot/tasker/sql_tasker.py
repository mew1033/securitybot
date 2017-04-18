'''
A tasker on top of a SQL database.
'''
import logging

from securitybot.tasker.tasker import Task, Tasker, STATUS_LEVELS, Escalation
from securitybot.sql import SQLEngine

from typing import List

# Note: this order is provided to match the SQLTask constructor
GET_ALERTS = '''
SELECT HEX(alerts.hash),
       title,
       alerts.ldap,
       reason,
       description,
       url,
       performed,
       comment,
       authenticated,
       status,
       event_time
FROM alerts
JOIN user_responses ON alerts.hash = user_responses.hash
JOIN alert_status ON alerts.hash = alert_status.hash
WHERE status = %s
'''

GET_ESCALATION = '''SELECT ldap, delay_in_sec, escalated_at FROM escalation WHERE hash=UNHEX(%s)'''
SET_ESCALATED = '''UPDATE escalation SET escalated_at=NOW() WHERE hash = UNHEX(%s) AND ldap=%s AND delay_in_sec=%s'''


class SQLTasker(Tasker):
    def _get_tasks(self, level):
        # type: (int) -> List[Task]
        '''
        Gets all tasks of a certain level.

        Args:
            level (int): One of STATUS_LEVELS
        Returns:
            List of SQLTasks.
        '''
        alerts = SQLEngine.execute(GET_ALERTS, (level,))
        logging.debug("DB result: {}".format(alerts))
        tasks = [SQLTask(*alert) for alert in alerts]

        for task in tasks:
            task.escalation = []
            escalation_list = SQLEngine.execute(GET_ESCALATION, (task.hash,))
            for escalation_tuple in escalation_list:
                task.escalation.append(Escalation(*escalation_tuple))
            logging.debug("Fetched task from DB: {0}".format(task))

        return tasks

    def get_new_tasks(self):
        # type: () -> List[Task]
        return self._get_tasks(STATUS_LEVELS.OPEN)

    def get_active_tasks(self):
        # type: () -> List[Task]
        return self._get_tasks(STATUS_LEVELS.INPROGRESS)

    def get_pending_tasks(self):
        # type: () -> List[Task]
        return self._get_tasks(STATUS_LEVELS.VERIFICATION)

SET_STATUS = '''
UPDATE alert_status
SET status=%s
WHERE hash=UNHEX(%s)
'''

SET_RESPONSE = '''
UPDATE user_responses
SET comment=%s,
    ldap=%s,
    performed=%s,
    authenticated=%s,
    updated_at=NOW()
WHERE hash=UNHEX(%s)
'''


class SQLTask(Task):
    def __init__(self, hsh, title, username, reason, description, url,
                 performed, comment, authenticated, status, event_time, escalation=None):
        # type: (str, str, str, str, str, str, bool, str, bool, int) -> None
        '''
        Args:
            hsh (str): SHA256 primary key hash.
        '''
        super(SQLTask, self).__init__(title, username, reason, description, url,
                                   performed, comment, authenticated, status, event_time=event_time, escalation=escalation)
        self.hash = hsh

    def _set_status(self, status):
        # type: (int) -> None
        '''
        Sets the status of a task in the DB.

        Args:
            status (int): The new status to use.
        '''
        self.status = status
        SQLEngine.execute(SET_STATUS, (status, self.hash))

    def _set_response(self):
        # type: () -> None
        '''
        Updates the user response for this task.
        '''
        SQLEngine.execute(SET_RESPONSE, (self.comment,
                                         self.username,
                                         self.performed,
                                         self.authenticated,
                                         self.hash))

    def set_open(self):
        self._set_status(STATUS_LEVELS.OPEN)

    def set_in_progress(self):
        self._set_status(STATUS_LEVELS.INPROGRESS)

    def set_verifying(self):
        self._set_status(STATUS_LEVELS.VERIFICATION)
        self._set_response()

    def is_verifying(self):
        return self.status == STATUS_LEVELS.VERIFICATION

    def set_escalated(self, escalation):
        escalation.set_notified()
        SQLEngine.execute(SET_ESCALATED, (self.hash, escalation.ldap, escalation.delay_in_sec))
