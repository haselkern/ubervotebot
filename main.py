###############################################################
# ubervotebot is a bot made for Telegram and was written by
# Lars Martens. It helps you manage polls and show the
# results in a variety of formats. This project was built
# ontop of @yukuku's telebot project.
###############################################################

import StringIO
import json
import logging
import random
import math
import urllib
import urllib2

# for sending images
from PIL import Image, ImageDraw, ImageFont
import multipart

# standard app engine imports
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
import webapp2

with open('TOKEN') as f:
    TOKEN = f.read()

BASE_URL = 'https://api.telegram.org/bot' + TOKEN + '/'

# ================================

STATE_DEFAULT = None

STATE_CREATE_POLL_CHOOSE_QUESTION = 'CREATE_POLL_CHOOSE_QUESTION'
STATE_CREATE_POLL_ADD_ANSWER = 'CREATE_POLL_ADD_ANSWER'
STATE_CREATE_POLL_CHOOSE_NUMBER_OF_ANSWERS = 'CREATE_POLL_CHOOSE_NUMBER_OF_ANSWERS'

STATE_DELETE_POLL = 'DELETE_POLL'
STATE_DELETE_POLL_CONFIRM = 'DELETE_POLL_CONFIRM'

STATE_RESULT_CHOOSE_POLL = 'RESULT_CHOOSE_POLL'
STATE_RESULT_CHOOSE_TYPE = 'RESULT_CHOOSE_TYPE'


RESULT_TYPE_LIST = 'list names'
RESULT_TYPE_NUMBERS = 'only count votes'
RESULT_TYPE_GRID = 'grid (like a doodle)'
RESULT_TYPE_BARS = 'bars'

# ================================

class User(ndb.Model):
    id = ndb.IntegerProperty()
    name = ndb.StringProperty()
    surname = ndb.StringProperty()

    activePoll = ndb.StringProperty() # the poll id the user is modifying at the moment
    activeState = ndb.StringProperty() # what operation is the user currently in
    polls = ndb.TextProperty() # stores polls and answers in json: [{...},{...}]

    def init(self):
        # load
        if not self.polls:
            self.polls_arr = []
        else:
            self.polls_arr = json.loads(self.polls)

    @classmethod
    def get(cls, user_obj=None, id=None):
        '''user_obj is the telegram user object that will get used for the id, and when a new user is created.
        Use id alternatively'''

        if user_obj:
            u = cls.query().filter(ndb.GenericProperty('id') == user_obj.get('id')).get()
            if not u:
                u = User(name=user_obj.get('first_name'), id=user_obj.get('id'), surname=user_obj.get('surname'))
            u.init()
            return u

        elif id:
            u = cls.query().filter(ndb.GenericProperty('id') == id).get()
            if u:
                u.init()
                return u
        # nothing was found or could be created
        return None
    
    @classmethod
    def create_random_poll_id(cls):
        o = []
        while len(o) < 5:
            c = random.randrange(ord('A'), ord('Z') + 1)
            o.append(chr(c))
        return ''.join(o)
    
    def create_valid_poll_id(self):
        '''Generates poll ids until we have found a valid one'''
        taken_ids = list(map(lambda x: x.get('id'), self.polls_arr))
        next_id = User.create_random_poll_id()
        while next_id in taken_ids:
            next_id = User.create_random_poll_id()
        return next_id

    # Find an existing poll
    def get_poll(self, id):
        for poll in self.polls_arr:
            if poll.get('id') == id:
                return poll
        return None
    
    def get_active_poll(self):
        return self.get_poll(self.activePoll)

    def delete_active_poll(self):
        if self.activePoll:
            self.polls_arr.remove(self.get_active_poll())
        self.activePoll = None

    def get_active_poll_answers(self):
        return self.get_active_poll()['answers']
    
    def get_name(self):
        '''Pretty print name'''
        o = self.name
        if self.surname:
            o += ' ' + self.surname
        return o

    # Create and store a new poll
    def new_poll(self):
        poll = {'id': self.create_valid_poll_id()}
        # Initialize arrays, so we can append stuff later
        poll['answers'] = []
        poll['answered'] = []
        poll['owner'] = self.id
        self.polls_arr.append(poll)
        return poll
    
    def serialize(self):
        self.polls = json.dumps(self.polls_arr)
        self.put()


# ================================

class MeHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'getMe'))))


class GetUpdatesHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'getUpdates'))))


class SetWebhookHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        url = self.request.get('url')
        if url:
            self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'setWebhook', urllib.urlencode({'url': url})))))

class WebhookHandler(webapp2.RequestHandler):
    def post(self):
        urlfetch.set_default_fetch_deadline(60)
        body = json.loads(self.request.body)
        logging.info('request body:')
        logging.info(body)
        self.response.write(json.dumps(body))

        update_id = body['update_id']

        # Return an inline keyboard for a poll
        def get_poll_inline_keyboard(poll, share_button=False):
            keys = '[]'
            if poll['answers']:
                keys = '['

                # iterate over answers
                for i in range(len(poll['answers'])):

                    answer = poll['answers'][i]
                    data = str(poll['owner']) + ';' + str(poll['id']) + ';' + str(i)

                    # Count how often answer at index i was voted for 
                    voted = 0
                    for user_answer in poll['answered']:
                        if user_answer['chosen_answers'] >> i & 1:
                            voted += 1

                    keys += '[{"text": "'+answer+' - '+str(voted)+'", "callback_data": "'+data+'"}],'

                if share_button:
                    keys += '[{"text": "share", "switch_inline_query": "'+poll.get('id')+'"}],'

                keys = keys[:-1] + ']' # removes the last comma
            return '{"inline_keyboard": '+keys+'}'

        
        def telegram_method(name, keyvalues):

            # encode strings
            encoded = {}
            for key in keyvalues:
                encoded[key] = keyvalues[key].encode('utf-8')

            resp = urllib2.urlopen(BASE_URL + name, urllib.urlencode(encoded)).read()

            logging.info(name+' response:')
            logging.info(resp)
        
        def send_image(img, chat_id, caption=''):
            resp = multipart.post_multipart(BASE_URL + 'sendPhoto', [
                ('chat_id', str(chat_id)),
                ('caption', caption),
                ('reply_markup', '{"hide_keyboard": true}')
            ], [
                ('photo', 'image.png', img),
            ])
        
        def count_binary_ones(n):
            ones = 0
            # number is 0 -> no bits to check
            if n == 0:
                return 0
            # max number of bits we need to check: int(math.log(n, 2))+1
            for i in range(int(math.log(n, 2))+1):
                if n >> i & 1:
                    ones += 1
            return ones


        # HANDLE INLINE QUERY
        if 'inline_query' in body:
            query = body['inline_query']
            inline_query_id = query['id']

            def send_inline_query_poll_result(poll):
                infos = {
                    'inline_query_id': str(inline_query_id),
                    'switch_pm_text': 'Create new poll',
                    'switch_pm_parameter': 'new'
                }
                if poll:
                    infos['results'] = '[{"type": "article", "id": "'+poll.get('id')+'", "title": "Click here to send poll", "description": "'+poll['question']+'", "thumb_url": "https://raw.githubusercontent.com/haselkern/ubervotebot/master/gfx/botpic.png", "input_message_content": {"message_text": "'+poll['question']+'"}, "reply_markup": '+get_poll_inline_keyboard(poll)+'}]'
                telegram_method('answerInlineQuery', infos)

            # find User
            user = User.get(query['from'])
            user.serialize()
            # find poll
            query_str = query['query']
            poll = user.get_poll(query_str)

            send_inline_query_poll_result(poll)

        # HANDLE CALLBACK_QUERY (from inline keyboards)
        elif 'callback_query' in body:

            # to send an update we need: (message_id and chat_id) or (inline_message_id)
            inline_message_id = None
            try:
                message = body['callback_query']['message']
                message_id = message.get('message_id')
                chat_id = message['chat'].get('id')
            except:
                inline_message_id = body['callback_query'].get('inline_message_id')
            data = body['callback_query']['data']
            user = User.get(body['callback_query']['from'])
            user.serialize()

            # sends a short status that the user will see for a few seconds on the top of the screen
            def ticker(msg):
                telegram_method('answerCallbackQuery', {
                    'callback_query_id': str(body['callback_query']['id']),
                    'text': msg
                })
            
            def update_keyboard(poll):

                # only show a share button in the chat with the bot
                share_button = not 'inline_message_id' in body['callback_query']
                
                infos = {
                    'text': poll['question'],
                    'reply_markup': get_poll_inline_keyboard(poll, share_button)
                }
                if inline_message_id:
                    infos['inline_message_id'] = inline_message_id
                else:
                    infos['chat_id'] = str(chat_id)
                    infos['message_id'] = str(message_id)
                telegram_method('editMessageText', infos)

            data = data.split(';')
            data[0] = int(data[0])
            data[2] = int(data[2])
            try:
                # find user the poll belongs to
                poll_owner = User.get(id=data[0])
                # find poll object
                poll = poll_owner.get_poll(data[1])

                if not poll:
                    ticker('This poll is no longer active')
                    return

                # get user answer
                user_answer = None
                for ua in poll['answered']:
                    if ua.get('user_id') == user.id:
                        user_answer = ua
                if not user_answer:
                    # append new user
                    user_answer = {'user_id': user.id, 'chosen_answers': 0}
                    poll['answered'].append(user_answer)
                
                # chosen_answers is an integer where the bits represent if an answer was chosen or not.
                # the rightmost bit represents the answer with index 0

                # old answers
                ua = user_answer['chosen_answers']
                # toggled bit, represents new answers
                ua_next = ua ^ (1 << data[2])

                # too many answers
                if count_binary_ones(ua_next) > poll['max_answers']:
                    ticker('You cannot select more than ' + str(poll['max_answers']) + ' answers.')
                # everything okay, save
                else:
                    user_answer['chosen_answers'] = ua_next
                    # send feedback
                    selected_answer = poll['answers'][data[2]]
                    if ua_next > ua:
                        ticker('You voted for: ' + selected_answer)
                    else:
                        ticker('You took your vote back.')
                
                # update poll display
                update_keyboard(poll)

                # save poll
                poll_owner.serialize()

            except Exception, e:
                # This exception occurs when we send an update that doesn't change the message or its keyboard
                # (or something unforeseen happens)
                logging.exception(e)

        elif 'chosen_inline_result' in body:
            # whatever this is, probably something important
            pass

        # HANDLE MESSAGES AND COMMANDS
        else:
            try:
                message = body['message']
            except:
                message = body['edited_message']

            message_id = message.get('message_id')
            date = message.get('date')
            text = message.get('text')
            fr = message['from']
            chat = message['chat']
            chat_id = chat['id']

            if not text:
                logging.info('no text')
                return

            def reply(msg, keyboard='{"hide_keyboard": true}'):
                telegram_method('sendMessage', {
                    'chat_id': str(chat_id),
                    'text': msg,
                    'disable_web_page_preview': 'true',
                    'reply_markup': keyboard
                })

            def send_action_photo():
                '''Sets status "sending picture" for this bot.'''
                telegram_method('sendChatAction', {
                    'chat_id': str(chat_id),
                    'action' : 'upload_photo'
                })
            
            
            # get User
            user = User.get(fr)
            
            def get_polls_keyboard():
                keys = '['
                for poll in user.polls_arr:
                    s = poll['id'] + ": " + poll['question']
                    keys += '["'+s+'"],'
                keys = keys[:-1] + ']'
                return '{"keyboard": '+keys+', "one_time_keyboard": true, "resize_keyboard": true}'
                

            if user.activeState == STATE_DEFAULT:

                if text == '/start':
                    # show help
                    with open("help.txt", "r") as f:
                        reply(f.read())

                elif text == '/new' or text == '/start new':
                    reply('Okay, a new poll. What should the question be?')
                    user.activeState = STATE_CREATE_POLL_CHOOSE_QUESTION
                
                elif text == '/delete':
                    if len(user.polls_arr) > 0:
                        reply('Choose a poll to delete or /cancel', keyboard=get_polls_keyboard())
                        user.activeState = STATE_DELETE_POLL
                    else:
                        reply('You have no polls to delete.')
                
                elif text == '/results':
                    if len(user.polls_arr) > 0:
                        reply('Choose a poll to show results from or /cancel', keyboard=get_polls_keyboard())
                        user.activeState = STATE_RESULT_CHOOSE_POLL
                    else:
                        reply('You have no polls you could show results from. Create one with /new')

                else:
                    # show help
                    with open('help.txt', 'r') as f:
                        reply(f.read())
            
            elif user.activeState == STATE_RESULT_CHOOSE_POLL:
                if text == '/cancel':
                    user.activeState = STATE_DEFAULT
                    reply('Okay, no results will be shown.')
                elif text.startswith('/'):
                    reply('Unrecognized command.')
                else:
                    poll_id = text[:5]
                    poll = user.get_poll(poll_id)
                    if poll:
                        user.activePoll = poll_id
                        user.activeState = STATE_RESULT_CHOOSE_TYPE
                        reply('How should the results be formatted?', keyboard='{"keyboard": [["'+RESULT_TYPE_LIST+'"],["'+RESULT_TYPE_NUMBERS+'"],["'+RESULT_TYPE_GRID+'"],["'+RESULT_TYPE_BARS+'"]], "resize_keyboard": true}')
                        
                    else:
                        reply('No poll with that id was found.')
                        user.activeState = STATE_DEFAULT
            
            elif user.activeState == STATE_RESULT_CHOOSE_TYPE:

                def can_create_image_with_dimensions(dimensions):
                    '''The image has to use less than 128MB in memory.
                    Check for a bit more, just to be safe. '''
                    return max(dimensions) ** 2 * 4 / (1000**2) < 100

                if text == '/cancel':
                    reply('Okay, no results will be shown.')
                    user.activeState = STATE_DEFAULT

                elif text == RESULT_TYPE_LIST:
                    # list names of voters
                    poll = user.get_active_poll()

                    msg = poll['question']+'\n- Results -\n'

                    for i in range(len(poll['answers'])):
                        names = []
                        for user_answer in poll['answered']:
                            # append user name if he has voted for this answer
                            if user_answer['chosen_answers'] >> i & 1:
                                u = User.get(id=user_answer['user_id'])
                                if u:
                                    names.append(u.get_name())
                        
                        msg += '\n' + poll['answers'][i] + '\n' + '('+str(len(names))+'): ' + ', '.join(names) + '\n'
                    
                    reply(msg)

                elif text == RESULT_TYPE_GRID:

                    send_action_photo()
                    
                    # create grid of results (like on doodle.com)
                    img_checked = Image.open('gfx/checked.png', 'r')
                    img_unchecked = Image.open('gfx/unchecked.png', 'r')
                    CELL_SIZE = max(img_checked.size)
                    FONT_SIZE = CELL_SIZE//2
                    SPACE = 20
                    font = ImageFont.truetype('gfx/Symbola.ttf', size=FONT_SIZE)

                    # organize data
                    poll = user.get_active_poll()
                    answers = poll['answers']
                    names = []
                    answered = []

                    for user_answer in poll['answered']:
                        # get user name
                        u = User.get(id=user_answer['user_id'])
                        names.append(u.get_name())
                        # get boolean array of answers
                        chosen_answers = user_answer['chosen_answers']
                        answered_row = []
                        for i in range(len(answers)):
                            answered_row.append(True if chosen_answers >> i & 1 else False)
                        answered.append(answered_row)

                    # get length of answers and names
                    longest_name = 0
                    for name in names:
                        l = font.getsize(name)[0]
                        if longest_name < l:
                            longest_name = l

                    longest_answer = 0
                    for answer in answers:
                        l = font.getsize(answer)[0]
                        if longest_answer < l:
                            longest_answer = l

                    # now we can create the image with optimal dimensions
                    dimen = (
                        longest_name + len(answers)*CELL_SIZE + 3*SPACE,
                        longest_answer + len(names)*CELL_SIZE + 3*SPACE
                        )

                    # Check for image size
                    if can_create_image_with_dimensions(dimen):

                        # we need a square image for nicer rotating, image will get cropped later
                        img = Image.new('RGB', (max(dimen), max(dimen)), '#FFF')
                        draw = ImageDraw.Draw(img)

                        # draw names right aligned and vertically centered
                        for i in range(len(names)):
                            l = font.getsize(names[i])[0]
                            draw.text((SPACE + (longest_name - l), longest_answer + i*CELL_SIZE + SPACE*2 + (CELL_SIZE-FONT_SIZE)//2), names[i], '#000', font)

                        # draw answers rotated
                        img = img.rotate(-90)
                        draw = ImageDraw.Draw(img)

                        for i in range(len(answers)):
                            draw.text((img.size[0] - longest_answer - SPACE, longest_name + i*CELL_SIZE + SPACE*2 + (CELL_SIZE-FONT_SIZE)//2), answers[i], '#000', font)

                        img = img.rotate(90)
                        draw = ImageDraw.Draw(img)

                        # draw grid
                        for x in range(len(answers)):
                            for y in range(len(names)):
                                # draw image for checked/unchecked
                                offset = (x * CELL_SIZE + longest_name + SPACE*2, y * CELL_SIZE + longest_answer + SPACE*2)
                                if answered[y][x]:
                                    img.paste(img_checked, offset)
                                else:
                                    img.paste(img_unchecked, offset)

                        # crop image
                        img = img.crop((0, 0, dimen[0], dimen[1]))

                        # send image
                        output = StringIO.StringIO()
                        img.save(output, 'PNG')
                        send_image(output.getvalue(), chat_id, (user.get_active_poll()['question']+' - results').encode('utf-8'))
                    else:
                        reply('The image would be too big to send you. Please choose a different result format.')


                elif text == RESULT_TYPE_BARS:

                    send_action_photo()

                    # bar chart
                    BAR_HEIGHT = 80
                    BAR_WIDTH = 400
                    FONT_SIZE = 40
                    SPACE = 10
                    font = ImageFont.truetype('gfx/Symbola.ttf', size=FONT_SIZE)

                    # organize data
                    poll = user.get_active_poll()
                    answers = poll['answers']
                    answered = []


                    # initialise answered to an array of 0s
                    for i in range(len(answers)):
                        answered.append(0)

                    # count votes
                    for user_answer in poll['answered']:
                        for i in range(len(answers)):
                            chosen_answers = user_answer['chosen_answers']
                            if chosen_answers >> i & 1:
                                answered[i] += 1

                    # normalize answered
                    answered = list(map(lambda x: float(x)/max(answered + [1,]), answered))
                    
                    # find longest answer in pixels
                    longest_answer = 0
                    for answer in answers:
                        l = font.getsize(answer)[0]
                        if longest_answer < l:
                            longest_answer = l

                    dimen = (longest_answer + BAR_WIDTH + 3*SPACE, len(answers)*(BAR_HEIGHT + SPACE) + SPACE)

                    # Check for image size
                    if can_create_image_with_dimensions(dimen):

                        img = Image.new('RGB', dimen, '#FFF')
                        draw = ImageDraw.Draw(img)

                        # draw bars
                        for i in range(len(answers)):
                            draw.text((SPACE, i*(BAR_HEIGHT + SPACE) + SPACE + (BAR_HEIGHT - FONT_SIZE)//2), answers[i], fill = '#000', font=font)
                            col = '#72d353'
                            if answered[i] == max(answered):
                                # special color for largest value
                                col = '#3f6de0'
                            draw.rectangle((longest_answer + SPACE*2, i*(BAR_HEIGHT + SPACE) +SPACE, BAR_WIDTH * answered[i] + longest_answer + SPACE*2, (i+1) * BAR_HEIGHT + (i+1)*SPACE), fill = col)

                            # draw text with percentage on bar
                            perc_text = str(int(round(answered[i] / sum(answered) * 100))) + '%'
                            perc_width = font.getsize(perc_text)[0]

                            # offset percentage text if it doesn't fit in the bar
                            perc_offset = 0
                            perc_color = '#fff'
                            if perc_width + 2*SPACE > BAR_WIDTH * answered[i]:
                                perc_offset = BAR_WIDTH * answered[i]
                                perc_color = '#000'

                            draw.text((longest_answer + SPACE*3 + perc_offset, i*(BAR_HEIGHT + SPACE) +SPACE*3),
                                perc_text,
                                fill = perc_color,
                                font = font
                                )

                        # send image
                        output = StringIO.StringIO()
                        img.save(output, 'PNG')
                        send_image(output.getvalue(), chat_id, (user.get_active_poll()['question']+' - results').encode('utf-8'))
                    else:
                        reply('The image would be too big to send you. Please choose a different result format.')

                else:
                    # just show number of votes
                    poll = user.get_active_poll()
                    msg = poll['question']+'\n- Results -\n'

                    # count bits for each answer
                    for i in range(len(poll['answers'])):
                        count = 0
                        for user_answer in poll['answered']:
                            if user_answer['chosen_answers'] >> i & 1:
                                count += 1
                        msg += '\n('+str(count)+') ' + poll['answers'][i]
                    
                    reply(msg)

                user.activePoll = None
                user.activeState = STATE_DEFAULT
                            

            
            elif user.activeState == STATE_DELETE_POLL:

                if text == '/cancel':
                    user.activeState = STATE_DEFAULT
                    reply('Nothing was deleted.')
                else:
                    poll_id = text[:5]
                    poll = user.get_poll(poll_id)
                    if poll:
                        title = poll['question']
                        reply('Do you really want to delete "'+title+'"?', keyboard='{"keyboard": [["yes", "no"]], "resize_keyboard": true}')
                        user.activePoll = poll_id
                        user.activeState = STATE_DELETE_POLL_CONFIRM
                    else:
                        reply('No poll with that id was found.')
                        user.activeState = STATE_DEFAULT
             
            elif user.activeState == STATE_DELETE_POLL_CONFIRM:

                if text == 'yes':
                    poll = user.get_active_poll()
                    title = poll['question']
                    user.delete_active_poll()
                    reply('Deleted "'+title+'"')
                else:
                    reply('Nothing was deleted.')

                user.activePoll = None
                user.activeState = STATE_DEFAULT

            elif user.activeState == STATE_CREATE_POLL_CHOOSE_QUESTION:

                if text == '/cancel':
                    user.delete_active_poll()
                    reply('Cancelled creating a poll.')
                    user.activeState = STATE_DEFAULT
                else:
                    # new poll
                    poll = user.new_poll()
                    poll['question'] = text.replace('"', '\'') # replace " with ' to prevent bad URLs. This is not nice, but it works
                    poll['question'] = poll['question']
                    user.activeState = STATE_CREATE_POLL_ADD_ANSWER
                    user.activePoll = poll['id']
                    reply('Now send the first answer to that question.')
            
            elif user.activeState == STATE_CREATE_POLL_ADD_ANSWER:

                if text == '/cancel':
                    user.delete_active_poll()
                    reply('Cancelled creating a poll.')
                    user.activeState = STATE_DEFAULT

                elif text == '/done':
                    poll = user.get_active_poll()

                    if len(poll['answers']) > 0:
                        # prompt for maximum number of answers a user can select
                        keys = []
                        cur_row = []
                        for i in range(len(poll['answers'])):
                            cur_row.append(str(i+1))
                            if len(cur_row) > 2 or i == len(poll['answers']) - 1:
                                # the row is finished, append to key array
                                keys.append(cur_row)
                                cur_row = []
                        # Convert array to well-formed string so that we can send it
                        keys = str(keys).replace('\'', '"')
                        
                        reply('How many options should each user be able to select?', keyboard='{"keyboard": '+keys+', "resize_keyboard": true}')

                        user.activeState = STATE_CREATE_POLL_CHOOSE_NUMBER_OF_ANSWERS
                    else:
                        # users shouldn't send /done without answers
                        reply('You have to send at least one answer! What should the first answer be?')
                else:
                    poll = user.get_active_poll()
                    poll['answers'].append(text.replace('"', '\''))  # replace " with ' to prevent bad URLs. This is not nice, but it works
                    reply('Cool, now send me another answer or type /done when you\'re finished.')
            
            elif user.activeState == STATE_CREATE_POLL_CHOOSE_NUMBER_OF_ANSWERS:

                if text == '/cancel':
                    user.delete_active_poll()
                    reply('Cancelled creating a poll.')
                    user.activeState = STATE_DEFAULT
                else:
                    n = -1
                    # try to parse number
                    try:
                        n = int(text)
                    except Exception, e:
                        logging.exception(e)

                    max_possible = len(user.get_active_poll_answers())

                    if n >= 1 and n <= max_possible:
                        poll = user.get_active_poll()
                        poll['max_answers'] = n
                        reply('That\'s it! Your poll is now ready:')

                        # print poll with share button
                        reply(poll['question'], keyboard=get_poll_inline_keyboard(poll, True))


                        user.activeState = STATE_DEFAULT
                        user.activePoll = None
                    else:
                        reply('Please enter a number between 1 and '+str(max_possible)+'!')

            else:
                reply('Whoops, I messed up. Please try again.\n(Invalid state: ' + str(user.activeState) + ')')
                user.activeState = STATE_DEFAULT
            
            # save everything
            user.serialize()


app = webapp2.WSGIApplication([
    ('/me', MeHandler),
    ('/updates', GetUpdatesHandler),
    ('/set_webhook', SetWebhookHandler),
    ('/webhook', WebhookHandler),
], debug=True)
