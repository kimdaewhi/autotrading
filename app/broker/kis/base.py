from app.core.settings import settings


class KISBase:
    def __init__(self, appkey: str, appsecret: str, url: str = settings.kis_base_url):
        self.appkey = appkey
        self.appsecret = appsecret
        self.url = url

    
    # ⚙️ KIS API 요청 시 필요한 공통 헤더 생성 메서드
    def build_headers(
        self,
        access_token: str,
        tr_id: str,
        content_type: str = "application/json;charset=utf-8",
        personalseckey: str = "",
        tr_cont: str = "",
        custtype: str = "P",
        seq_no: str = "",
        mac_address: str = "",
        phone_number: str = "",
        ip_addr: str = "",
        gt_uid: str = "",
    ) -> dict:
        return {
            "Content-Type": content_type,
            "Authorization": f"Bearer {access_token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "personalseckey": personalseckey,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": custtype,
            "seq_no": seq_no,
            "mac_address": mac_address,
            "phone_number": phone_number,
            "ip_addr": ip_addr,
            "gt_uid": gt_uid,
        }