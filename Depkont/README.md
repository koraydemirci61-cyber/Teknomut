# Depkont

Depo kontrol paneli. Açılışta SAP oturumunu hazırlar.

- Oturum açıksa pencere öne gelir ve SAP ana ekranına döner.
- Oturum yoksa `C:\Program Files (x86)\SAP\FrontEnd\SAPgui\saplogon.exe` açılır ve **SAP DESTEK** bağlantısından giriş yapılır. İstemci, giriş ekranında yazılı olan değerdir. Şifre ekrana yazılmaz. Başka ekranlarda açık kalan oturumlar kapatılmaz.
- 15 haneli seri okutulduğunda veya yapıştırıldığında ana ekrandan ZSERI1 açılır. Değer **Destek Seri numarası** alanına, sonda `V` yoksa eklenerek yazılır ve sorgulanır.
- Sonuç boşsa raporda `satın alması yok` yazar. Doluysa son satırdaki depo yeri rapora eklenir. Her satırın sıra numarası vardır. Rapor kopyalanabilir, **Temizle** ile silinir ve **Excel** ile `.xlsx` dosyasına kaydedilir.
- Alttaki listenin solunda satır sıra numarası görünür. Liste **Sorgula** ile aynı şekilde toplu sorgulanır. **Durdur**, o anda süren sorguyu bitirir ve henüz başlamamış serileri atlar. Başka SAP oturumları kapatılmaz.

## Çalıştırma

`Depkont` klasöründeyken:

```powershell
python -m depkont
python -m depkont --version
```

## Başka bilgisayar

`dist\Depkont.exe` tek dosyadır. Karşı bilgisayarda Python kurulu olması gerekmez. Windows 64 bit olmalıdır.

Karşı bilgisayarda SAP GUI kurulu olmalı, SAP GUI betiklemesi açık olmalı ve SAP Logon listesinde **SAP DESTEK** bağlantısı bulunmalıdır. Program, bu bilgisayardaki hesapla giriş yapar. Dosyayı yalnızca bu hesabın kullanılacağı bilgisayara kopyalayın.

Exe imzasız olduğu için Windows SmartScreen uyarı verebilir. Dosya sizin derlemenizse çalıştırmaya devam edilebilir.

Yeniden derlemek için, `Depkont` klasöründeyken:

```powershell
pyinstaller --noconfirm depkont.spec
```

## Test

```powershell
python -m unittest discover -s tests
```

## Kurulum

Komut satırından `depkont` olarak çalıştırmak için:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```
