from android import activity
from android.permissions import request_permissions, Permission
from android.runnable import run_on_ui_thread
from android.storage import app_storage_path
from jnius import autoclass, cast
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
from kivy.properties import StringProperty, ObjectProperty
from kivy.clock import mainthread
from re import match
from time import sleep
from json import dumps, load
from socket import socket, AF_INET, SOCK_STREAM
from base64 import b64encode
from re import match as reMatch
from re import sub as reSub
from threading import Thread
import hmac



# Anotaan oikeudet käyttää NFC:tä ja verkkokorttia.
request_permissions([Permission.NFC, Permission.INTERNET, ])

# Tuodaan tarvittavat Java-luokat.
NfcAdapter = autoclass('android.nfc.NfcAdapter')
PythonActivity = autoclass('org.kivy.android.PythonActivity')
Intent = autoclass('android.content.Intent')
PendingIntent = autoclass('android.app.PendingIntent')
NdefRecord = autoclass('android.nfc.NdefRecord')
NdefMessage = autoclass('android.nfc.NdefMessage')
Tag = autoclass('android.nfc.Tag')
Process = autoclass('java.lang.Process')
Runtime = autoclass('java.lang.Runtime')
DataOutputStream = autoclass('java.io.DataOutputStream')
Apduhandler = autoclass('fi.toikkaroijat.nfc_mimic.ServiceApduhandler')



# Etsi syötteestä validi IP-osoite ja palauta se kutsujalle.
def isValidSocket(possibleSocket: str):

    isValid = match(r'^(?!0)(?:(?=2[1-5][1-5])\d{3}|(?=1\d{2})\d{3}|\d{1,2})\.(?:(?=2[1-5][1-5])\d{3}|(?=1\d{2})\d{3}|\d{1,2})\.(?:(?=2[1-5][1-5])\d{3}|(?=1\d{2})\d{3}|\d{1,2})\.(?:(?=2[1-5][1-5])\d{3}|(?=1\d{2})\d{3}|\d{1,2}):(?!0)(?:(?=[1-6][1-5][1-5][1-3][1-5])\d{1,5}|\d{1,4})$', possibleSocket)

    if (isValid):
        return True
    else:
        return False
    

def isValidUid(possibleUid: str, ranged=False):

    regexMatches = match(r'^(?P<startUid>[\da-fA-F]{8})-(?P<endUid>[\da-fA-F]{8})?$', possibleUid)

    if (regexMatches and ranged):
        return regexMatches
    elif (regexMatches and not(ranged)):
        return True
    else:
        return False


def isValidKey(possibleKey: str) -> bool:

    isValid = match('^\w{8,64}$', possibleKey)

    if (isValid):
        return True
    else:
        return False
        


class Sm(ScreenManager):

    bruteUidOptions = {

        'stopBruteUidThreadFlag': True,
        'bruteUidThread': None,
        'currentUid': None,
        'startUid': None,
        'endUid': None

    }

    socketInputWidget = ObjectProperty(None)
    socketInstructionLabel = StringProperty('Kirjoita vastaanottavan palvelimen IP-osoite ja portti')

    uidInputWidget = ObjectProperty(None)
    uidInstructionLabel = StringProperty('Kirjoita kulkutunnisteen UID')

    bruteUidInputWidget = ObjectProperty(None)
    # bruteUidInstructionLabel = StringProperty('Kirjoita lukija-avaimesi')

    cloneTagStatus = StringProperty('NFC-lukija valmiina tagin kloonausta varten')
    uidBruteStatus = StringProperty('Määritä arvattavat UID:t')
    errorLabel = StringProperty('Virhe.')

    cloneTagSuccessStatus = StringProperty('Kulkutunnisteen kloonaus onnistui.')


    # Metodi tarkastaa, onko käyttäjä korjannut virheilmoituksessa mainitut puutteet ja vaihtaa näkymän aloitusruutuun.
    @mainthread
    def retry(self):

        if (app.ndefReceptionEnabled):

            app.errorPending = False
            app.initNfcReader()

        app.errorPending = False
        app.root.current = 'startScreen'


    # Tarkasta käyttäjän syöttämä IP-osoite.
    @mainthread
    def saveAndValidateConfig(self):

        app.root.socketInstructionLabel = 'Kirjoita vastaanottavan palvelimen IP-osoite ja portti'
        app.root.keyInstructionLabel = 'Kirjoita lukija-avaimesi'

        insertedSocket = str(self.socketInputWidget.text)
        insertedKey = str(self.keyInputWidget.text)

        if (isValidSocket(insertedSocket) and isValidKey(insertedKey)):
            try:
                with open('config.json', 'w') as configFile:

                    config = {

                        'readerKey': insertedKey,
                        'serverSocket': insertedSocket

                    }

                    configFile.write(dumps(config))

                    app.serverSocket = insertedSocket.split(':')
                    app.serverSocket[1] = int(app.serverSocket[1])
                    app.serverSocket = tuple(app.serverSocket)
                    app.readerKey = insertedKey

                self.current = 'cloneTagScreen'
                app.enableNdefReception()
                app.ndefReceptionEnabled = True

            except:

                self.handleEvent(errorMsg='Konfiguraation talletus ei onnistunut. Varmista, että laitteessasi on vapaata tallennustilaa käytettävissä ja yritä uudelleen.')

        else:

            if (not(isValidKey(insertedKey))):
                self.keyInstructionLabel = 'Syötä validi avain.'
            
            if (not(isValidSocket(insertedSocket))):
                self.socketInstructionLabel = 'Syötä validi IP-osoite ja portti.'


    @mainthread
    def changeUid(self):

        insertedUid = str(self.uidInputWidget.text)

        if (isValidUid(insertedUid)):
            if (app.defaultNfcAdapter.isEnabled()):

                writeSuccessful = app.writeNxpConf(insertedUid)

                if (writeSuccessful):

                    app.reinitNfcc()

                    self.cloneTagSuccessStatus = 'UID-tunnisteen vaihto onnistui.'
                    self.changeScreen('cloneTagSuccessScreen')

                else:
                    app.handleEvent(errorMsg='UID-tunnisteen tallennus ei onnistunut. Varmista, että sovelluksella on root-tason oikeudet.')

            else:
                app.handleEvent(errorMsg='NFC ei ole päällä. Käynnistä NFC ja yritä uudelleen.')

        else:
            self.uidInstructionLabel = 'Syötä validi UID.'


    @mainthread
    def changeScreen(self, screenName: str) -> None:
        self.current = f'{screenName}'


    def initUidCloning(self):
        
        app.initNfcReader()
        self.current = 'cloneTagScreen'


    def initUidBrute(self):

        self.changeScreen('uidBruteScreen')

        self.bruteUidThread = Thread(target=self.bruteUids)
        self.bruteUidOptions['stopBruteUidThreadFlag'] = True
        self.bruteUidThread.start()

        self.uidBruteStatus = 'Määritä arvattavat UID:t'

        # hex((int(testHex, base=16)) + 1)[2:]


    def beginUidBrute(self):

        uidMatches = isValidUid(self.bruteUidInputWidget.text, ranged=True)

        if ((uidMatches.group('startUid') and uidMatches.group('endUid'))):

            startUid = uidMatches.group('startUid')
            endUid = uidMatches.group('endUid')

            if ((int(endUid, base=16) - int(startUid, base=16)) > 0):

                app.execShellCmd(f'mount -o rw,remount /system', app.outputStream)

                if (self.bruteUidOptions['currentUid'] is None):
                    self.bruteUidOptions['currentUid'] = self.bruteUidOptions['startUid'] = startUid

                self.bruteUidOptions['endUid'] = endUid
                
                self.bruteUidOptions['stopBruteUidThreadFlag'] = False

                self.ids.bruteUidBeginButton.disabled = True
                self.ids.bruteUidStopButton.disabled = False

            else:
                self.uidBruteStatus = 'Syötä validi vaihteluväli.'

        else:
            self.uidBruteStatus = 'Syötä validi vaihteluväli.'


    def stopUidBrute(self):
        
        self.uidBruteStatus = 'Lopetetaan arvailu...'
        app.execShellCmd(f'mount -o ro,remount /system', app.outputStream)
        
        self.bruteUidOptions['stopBruteUidThreadFlag'] = True
        self.ids.bruteUidBeginButton.disabled = False
        self.ids.bruteUidStopButton.disabled = True

        self.uidBruteStatus = f'Viimeisin UID: {self.bruteUidOptions["currentUid"].upper()}'


    # UID Brute -säie käyttää tätä metodia statuksen päivitykseen.
    @mainthread
    def updateBruteStatus(self, labelText: str):
        self.uidBruteStatus = labelText


    # UID-tunnisteuden brutetukseen käytettävä metodi.
    def bruteUids(self):

        while (True):

            if (not(self.bruteUidOptions['stopBruteUidThreadFlag'])):

                currentUid = self.bruteUidOptions["currentUid"]
                endUid = self.bruteUidOptions['endUid']

                if (not(int(currentUid, base=16) > int(endUid, base=16))):

                    self.updateBruteStatus(f'UID: {currentUid.upper()}')
                    sleep(0.5)

                    try:
                        with open(f'{app_storage_path()}/libnfc-nxp.conf', 'r+') as nxpConfFile:

                            tagUidFormatted = currentUid.upper()
                            conf = nxpConfFile.read()

                            replString = ', '.join([tagUidFormatted[i:i+2] for i in range(0, len(tagUidFormatted), 2)])
                            conf = reSub(r'(NXP_CORE_CONF={(?:\s+?[0-9A-F]{2},){25}\s+?33,\s0[47A],\s)(?P<uidBytes>(?:[\dA-F]{2},\s){3}[\dA-F]{2})([\s\dA-F,]+})', fr'\g<1>{replString}\g<3>', conf)
                            
                            nxpConfFile.seek(0, 0)
                            nxpConfFile.write(conf)
                            nxpConfFile.truncate()

                        app.execShellCmd(f'cp {app_storage_path()}/libnfc-nxp.conf /etc/libnfc-nxp.conf', app.outputStream)
                        # app.execShellCmd(f'chown root:root /etc/libnfc-nxp.conf', app.outputStream)crea
                        # app.execShellCmd(f'chmod 644 /etc/libnfc-nxp.conf', app.outputStream)

                        app.reinitNfcc()
                    
                    except:
                        self.stopUidBrute()

                    self.bruteUidOptions['currentUid'] = hex((int(currentUid, base=16)) + 1)[2:]

                else:
                    self.stopUidBrute()


    def closeApp(self):

        app.execShellCmd('exit', app.outputStream)
        exit(0)



class NfcMimicApp(App):

    def __init__(self, **kwargs):

        super().__init__(**kwargs)
        self.readerKey = self.serverSocket = self.suProcess = self.outputStream = None
        self.ndefReceptionEnabled = self.errorPending = False

        self.currentActivity = PythonActivity.mActivity
        self.defaultNfcAdapter = NfcAdapter.getDefaultAdapter(self.currentActivity)
        # self.initNfcReader()
        # self.loadConfig()


    def loadConfig(self):

        self.readerKey = None
        self.serverSocket = None

        try:
            with open('config.json', 'r') as configFile:

                config = load(configFile)
                tempReaderKey, tempServerSocket = config['readerKey'], config['serverSocket']

                if (isValidKey(tempReaderKey) and isValidSocket(tempServerSocket)):
                    self.readerKey = tempReaderKey

                    self.serverSocket = tempServerSocket.split(':')
                    self.serverSocket[1] = int(self.serverSocket[1])
                    self.serverSocket = tuple(self.serverSocket)

                    self.root.current = 'cloneTagScreen'

        except:
            pass

        if ((self.readerKey is None) or (self.serverSocket is None)):
            self.handleEvent(improperConfig=True)


    def initNfcReader(self):

        if (self.defaultNfcAdapter):
            if (self.defaultNfcAdapter.isEnabled()):
    
                # Määritetään PendingIntent-objektin avulla välitettävä Intent-objekti tälle ohjelmalle.
                self.NfcPendingIntent = PendingIntent.getActivity(
                    self.currentActivity,
                    0,
                    Intent(
                        self.currentActivity,
                        self.currentActivity.getClass()
                    ).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), # Ei luoda uutta Activity-instanssia, jos olemassa oleva instanssi on
                    0                                            # backstack-pinon päällimmäinen Activity-instanssi.
                )

                # Estetään NDEF-viestien lähetys ja deaktivoidaan NDEF-viestien vastaanotto sovelluksen käynnistyessä.
                self.enableNdefReception()
                self.ndefReceptionEnabled = True
                self.disableNdefPushing()

            else:
                self.handleEvent(errorMsg='Virhe: NFC ei ole päällä. Aseta NFC päälle ja yritä uudelleen.')

        else:
            self.handleEvent(errorMsg='Virhe: Laitteesi ei tue NFC-ominaisuutta.')


    # Funktio lähettää viestin palvelimelle ja palauttaa totuusarvon True, jos lähetys onnistui.
    def sendToServer(self, msg: str, serverSocket: tuple) -> bool:

        try:
            with socket(AF_INET, SOCK_STREAM) as tcpSocket:

                # Yhdistä palvelimeen ja lähetä ID-tunnus JSON-muodossa.
                tcpSocket.settimeout(15)
                tcpSocket.connect(serverSocket)
                tcpSocket.sendall(bytes(msg, 'UTF-8'))

            return True
        
        except:

            return False


    @mainthread
    def handleEvent(self, improperConfig=False, errorMsg='Virhe.'):

        self.disableNdefPushing()
        self.disableNdefReception()
        self.ndefReceptionEnabled = False

        if (improperConfig and not(self.errorPending)):

            self.root.socketInstructionLabel = 'Kirjoita vastaanottavan palvelimen IP-osoite ja portti'
            self.root.keyInstructionLabel = 'Kirjoita lukija-avaimesi'
            self.root.current = 'askForConfigScreen'

        else:

            self.errorPending = True
            self.root.errorLabel = errorMsg
            self.root.current = 'errorScreen'


    def computeHmac(self, key, msg) -> bytes:

        Hmac = hmac.new(key.encode('UTF-8'), msg=msg.encode('UTF-8'), digestmod='sha3_512')
        return b64encode(Hmac.digest())


    def execShellCmd(self, command: str, outputStream) -> None:

        outputStream.writeBytes(f'{command}\n')
        outputStream.flush()


    def reinitNfcc(self):

        self.execShellCmd(f'service call nfc 5', self.outputStream)
        while (app.defaultNfcAdapter.isEnabled()):
            sleep(0.1)

        self.execShellCmd(f'service call nfc 6', self.outputStream)
        while (not(app.defaultNfcAdapter.isEnabled())):
            sleep(0.1)


    def writeNxpConf(self, tagUid: str) -> bool:

        try:
            # self.execShellCmd(f'cp /etc/libnfc-nxp.conf {app_storage_path()}', self.outputStream)
            # self.execShellCmd(f'chmod 666 {app_storage_path()}/libnfc-nxp.conf', self.outputStream)

            while (True):

                sleep(0.01)

                try:
                    with open(f'{app_storage_path()}/libnfc-nxp.conf', 'r+') as nxpConfFile:

                        tagUidFormatted = tagUid.upper()
                        conf = nxpConfFile.read()

                        replString = ', '.join([tagUidFormatted[i:i+2] for i in range(0, len(tagUidFormatted), 2)])
                        conf = reSub(r'(NXP_CORE_CONF={(?:\s+?[0-9A-F]{2},){25}\s+?33,\s0[47A],\s)(?P<uidBytes>(?:[\dA-F]{2},\s){3}[\dA-F]{2})([\s\dA-F,]+})', fr'\g<1>{replString}\g<3>', conf)
                        
                        nxpConfFile.seek(0, 0)
                        nxpConfFile.write(conf)
                        nxpConfFile.truncate()

                    break
                
                except:
                    continue

            self.execShellCmd(f'mount -o rw,remount /system', self.outputStream)
            self.execShellCmd(f'cp {app_storage_path()}/libnfc-nxp.conf /etc/libnfc-nxp.conf', self.outputStream)

            # self.execShellCmd(f'chown root:root /etc/libnfc-nxp.conf', self.outputStream)
            # self.execShellCmd(f'chmod 644 /etc/libnfc-nxp.conf', self.outputStream)
            self.execShellCmd(f'mount -o ro,remount /system', self.outputStream)

            return True

        except:
            return False


    def on_new_intent(self, intent):

        try:

            if (app.defaultNfcAdapter.isEnabled()):

                app.root.cloneTagStatus = 'Käsitellään...'
                self.ndefReceptionEnabled = False
                self.disableNdefReception()

                if ((intent.getAction()) == NfcAdapter.ACTION_TAG_DISCOVERED):
                    
                    tag = intent.getParcelableExtra(NfcAdapter.EXTRA_TAG)
                    tag = cast(Tag, tag)

                    tagUid = str(bytearray(tag.getId()).hex()).upper()

                    # Tallennetaan tagi
                    # with open('tags.json', 'w') as tagsFile:
                    #     tagsFile.write(dumps({'0': tagUidHex}))

                    app.root.cloneTagStatus = 'Kloonataan tunnistetta...'

                    writeSucceeded = self.writeNxpConf(tagUid)
                    if (writeSucceeded):

                        self.reinitNfcc()

                        app.root.cloneTagSuccessStatus = f"Kulkutunniste '{tagUid}' kloonattu onnistuneesti."
                        app.root.changeScreen('cloneTagSuccessScreen') # Tämä ajetaan Androidilla jostain syystä toisessa säikeessä, siksi suoritus pakotetaan pääsäikeeseen.

                    else:
                        self.handleEvent(errorMsg='Kulkutunnisteen kloonaus ei onnistunut. Tarkasta, että sovelluksella on root-tason oikeudet.')

                else:
                    app.root.cloneTagStatus = "Action ei täsmää."

                self.enableNdefReception()
                self.ndefReceptionEnabled = True
                app.root.cloneTagStatus = 'NFC-lukija valmiina tagin kloonausta varten'

            else:
                self.handleEvent(errorMsg='Virhe: NFC ei ole päällä. Aseta NFC päälle ja yritä uudelleen.')

        except:
            self.handleEvent(errorMsg='Virhe: Kulkutunnisteen kloonaus epäonnistui. Varmista, että sovelluksella on root-tason oikeudet.')


    @mainthread
    @run_on_ui_thread
    def disableNdefPushing(self):
        self.defaultNfcAdapter.setNdefPushMessage(None, self.currentActivity)


    # NDEF-viestien vastaanoton aktivointi.
    @mainthread
    @run_on_ui_thread
    def enableNdefReception(self):

        # Aktivoidaan NFC-tagien/NDEF-viestien-vastaanottojärjestelmä. Asetetaan IntentFilter- ja techLists-parametrien arvoksi None, 
        # jotta kaikki vastaanotetut viestit käsitellään. Vastaanotettujen viestien suodatusta tulee muuttaa, jos sovelluskehitystä jatketaan.
        self.defaultNfcAdapter.enableForegroundDispatch(self.currentActivity, self.NfcPendingIntent, None, None)
        activity.bind(on_new_intent=self.on_new_intent)


    # NDEF-viestien vastaanoton deaktivointi.
    @mainthread
    @run_on_ui_thread
    def disableNdefReception(self):

        self.defaultNfcAdapter.disableForegroundDispatch(self.currentActivity)
        activity.unbind(on_new_intent=self.on_new_intent)


    def on_start(self):

        # self.initNfcReader()
        # self.loadConfig()

        # Taustaohjelman käynnistys
        # Apduhandler.start(PythonActivity.mActivity, '')

        # Anotaan root-oikeuksia.
        self.suProcess = Runtime.getRuntime().exec("su")
        self.outputStream = DataOutputStream(self.suProcess.getOutputStream())

        app.execShellCmd(f'cp /etc/libnfc-nxp.conf {app_storage_path()}', app.outputStream)
        app.execShellCmd(f'chmod 666 {app_storage_path()}/libnfc-nxp.conf', app.outputStream)


    def on_resume(self):

        if (self.ndefReceptionEnabled):
            self.enableNdefReception()
        else:
            self.disableNdefReception()


    def on_pause(self):

        self.disableNdefReception()
        return True



app = NfcMimicApp()
app.run()