global logger
import logging
import threading
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    JSON,
    TypeDecorator,
    types,
)
from sqlalchemy.orm import sessionmaker
import json
import var
import main
import pandas as pd
from pyautogui import alert
from pyairtable import Table
from pyairtable.formulas import match
import os
import datetime
import traceback
import queue
from var import logger
import re

db_path = var.base_dir + "/group.DB"
Base = declarative_base()
engine = create_engine(
    f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
)


class Json(TypeDecorator):

    @property
    def python_type(self):
        return object

    impl = types.String

    def process_bind_param(self, value, dialect):
        return json.dumps(value)

    def process_literal_param(self, value, dialect):
        return value

    def process_result_value(self, value, dialect):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None


class Group_A(Base):
    __tablename__ = "group_a"
    id = Column(Integer, primary_key=True)
    FIRSTFROMNAME = Column(String)
    LASTFROMNAME = Column(String)
    EMAIL = Column(String)
    EMAIL_PASS = Column(String)
    PROXY_PORT = Column(String)
    PROXY_USER = Column(String)
    PROXY_PASS = Column(String)


class Group_B(Base):
    __tablename__ = "group_b"
    id = Column(Integer, primary_key=True)
    FIRSTFROMNAME = Column(String)
    LASTFROMNAME = Column(String)
    EMAIL = Column(String)
    EMAIL_PASS = Column(String)
    PROXY_PORT = Column(String)
    PROXY_USER = Column(String)
    PROXY_PASS = Column(String)


class Targets(Base):
    __tablename__ = "targets"
    id = Column(Integer, primary_key=True)
    one = Column(String)
    two = Column(String)
    three = Column(String)
    four = Column(String)
    five = Column(String)
    six = Column(String)
    TONAME = Column(String)
    EMAIL = Column(String)


class CachedTargets(Base):
    __tablename__ = "cached_targets"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)


class FollowUp(Base):
    __tablename__ = "follow_up"
    id = Column(Integer, primary_key=True)
    group_email = Column(String)
    group_info = Column(JSON)
    target_email = Column(String)
    target_info = Column(JSON)
    campaign_id = Column(String)
    email_subject = Column(String)
    campaign_time = Column(DateTime)


Base.metadata.create_all(engine)


def get_session():
    Session = sessionmaker(bind=engine)
    session = Session()
    return session


class Database:

    def __init__(self):
        """initialize the class"""
        self.logger = logger
        Session = sessionmaker(bind=engine)
        self.session = Session()
        self.table = {
            "group_a": Group_A,
            "group_b": Group_B,
            "targets": Targets,
            "cached_targets": CachedTargets,
            "follow_up": FollowUp,
        }

    def remove(self, table=None, id=None):
        """remove row from table by id and this method expects
        two arguments table and id of that row"""
        try:
            if table is not None and id is not None:
                objects = self.session.query(self.table[table]).get(int(id))
                if objects:
                    self.session.delete(objects)
                    self.session.commit()
                    self.logger.info(f"Deleted id - {id}")
                    return True
            else:
                print("please provide table and id")
                return False
        except Exception as e:
            self.session.rollback()
            self.logger.error(f"Error at Database.remove() - {e}")
            return False

    def get_cached_targets(self):
        results = [item.email for item in self.session.query(CachedTargets).all()]
        return results

    def add_to_cached_targets(self, email):
        try:
            if (
                not self.session.query(CachedTargets)
                .filter(CachedTargets.email == email)
                .first()
            ):
                cached_targets = CachedTargets(email=email)
                self.session.add(cached_targets)
                self.session.commit()
            else:
                self.logger.info("Database.add_to_cached_targets() - Already Exists")
        except Exception as e:
            self.session.rollback()
            self.logger.error(f"Error at Database.add_to_cached_targets() - {e}")

    def remove_cached_target(self, email):
        try:
            self.session.query(CachedTargets).filter(
                CachedTargets.email == email
            ).delete()
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            self.logger.error(f"Error at Database.remove_cached_target() - {e}")

    def clear_cached_targets(self):
        try:
            self.session.query(CachedTargets).delete()
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            self.logger.error(f"Error at Database.clear_cached_targets() - {e}")

    def get_all_followup(self, campaign_id=None):
        if campaign_id:
            results = [
                {
                    "id": item.id,
                    "group_email": item.group_email,
                    "group_info": item.group_info,
                    "target_email": item.target_email,
                    "target_info": item.target_info,
                    "campaign_id": item.campaign_id,
                    "campaign_time": item.campaign_time,
                }
                for item in self.session.query(FollowUp)
                .filter(FollowUp.campaign_id == campaign_id)
                .all()
            ]
            return results
        return None

    def add_follow_up(self, list_of_dict: list):
        try:
            follow_ups = [
                dict(
                    group_email=item["group_email"],
                    group_info=item["group_info"],
                    target_email=item["target_email"],
                    target_info=item["target_info"],
                    campaign_id=item["campaign_id"],
                    campaign_time=item["campaign_time"],
                )
                for item in list_of_dict
            ]
            self.session.bulk_insert_mappings(FollowUp, follow_ups)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            self.logger.error(
                f"Error at Database.add_follow_up() - {e}\n{traceback.format_exc()}"
            )
            return False

    def delete_all_followup(self, campaign_id=None):
        try:
            self.session.query(FollowUp).filter(
                FollowUp.campaign_id == campaign_id
            ).delete()
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            self.logger.error(f"Error at Database.delete_all_followup() - {e}")
            return False


def db_update_row(row):
    try:
        session = get_session()
        if main.GUI.radioButton_db_groupa.isChecked():
            objects = session.query(Group_A).get(int(row["ID"]))
            objects.FIRSTFROMNAME = row["FIRSTFROMNAME"]
            objects.LASTFROMNAME = row["LASTFROMNAME"]
            objects.EMAIL = row["EMAIL"]
            objects.EMAIL_PASS = row["EMAIL_PASS"]
            objects.PROXY_PORT = row["PROXY:PORT"]
            objects.PROXY_USER = row["PROXY_USER"]
            objects.PROXY_PASS = row["PROXY_PASS"]
        elif main.GUI.radioButton_db_groupb.isChecked():
            objects = session.query(Group_B).get(int(row["ID"]))
            objects.FIRSTFROMNAME = row["FIRSTFROMNAME"]
            objects.LASTFROMNAME = row["LASTFROMNAME"]
            objects.EMAIL = row["EMAIL"]
            objects.EMAIL_PASS = row["EMAIL_PASS"]
            objects.PROXY_PORT = row["PROXY:PORT"]
            objects.PROXY_USER = row["PROXY_USER"]
            objects.PROXY_PASS = row["PROXY_PASS"]
        else:
            objects = session.query(Targets).get(int(row["ID"]))
            objects.one = row["1"]
            objects.two = row["2"]
            objects.three = row["3"]
            objects.four = row["4"]
            objects.five = row["5"]
            objects.six = row["6"]
            objects.TONAME = row["TONAME"]
            objects.EMAIL = row["EMAIL"]
        session.commit()
        print("DB updated")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error at db_update_row - {e}")
        return False


def db_remove_row(id):
    try:
        session = get_session()
        if main.GUI.radioButton_db_groupa.isChecked():
            objects = session.query(Group_A).get(id)
        elif main.GUI.radioButton_db_groupb.isChecked():
            objects = session.query(Group_B).get(id)
        else:
            objects = session.query(Targets).get(id)
        if objects:
            session.delete(objects)
            session.commit()
            print("DB updated")
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error at var.db_remove_row - {e}")
        return False


def db_remove_rows(ids):
    try:
        session = get_session()
        for id in ids:
            if main.GUI.radioButton_db_groupa.isChecked():
                objects = session.query(Group_A).get(id)
            elif main.GUI.radioButton_db_groupb.isChecked():
                objects = session.query(Group_B).get(id)
            else:
                objects = session.query(Targets).get(id)
            if objects:
                session.delete(objects)
        session.commit()
        print("DB updated")
    except Exception as e:
        session.rollback()
        logger.error(f"Error at var.db_remove_rows - {e}")


def db_insert_row():
    try:
        session = get_session()
        if main.GUI.radioButton_db_groupa.isChecked():
            objects = Group_A(
                FIRSTFROMNAME="",
                LASTFROMNAME="",
                EMAIL="",
                EMAIL_PASS="",
                PROXY_PORT="",
                PROXY_USER="",
                PROXY_PASS="",
            )
        elif main.GUI.radioButton_db_groupb.isChecked():
            objects = Group_B(
                FIRSTFROMNAME="",
                LASTFROMNAME="",
                EMAIL="",
                EMAIL_PASS="",
                PROXY_PORT="",
                PROXY_USER="",
                PROXY_PASS="",
            )
        else:
            objects = Targets(
                one="", two="", three="", four="", five="", six="", TONAME="", EMAIL=""
            )
        session.add(objects)
        session.commit()
        logger.info("DB updated")
        return (True, objects.id)
    except Exception as e:
        session.rollback()
        logger.error(f"Error at var.db_insert_row - {e}")
        return (False, None)

def update_target_verified():
    session = get_session()
    try:
        clear_table(target=True)
        target = var.target[["1", "2", "3", "4", "5", "6", "TONAME", "EMAIL"]]
        target.fillna(" ", inplace=True)
        target = target.astype(str)
        target = target.loc[target["EMAIL"] != " "]
        if len(var.target_blacklist) > 0:
            target = target[
                ~target["EMAIL"]
                .str.lower()
                .str.contains("|".join(var.target_blacklist))
            ]
        if len(target) > 0:
            objects = [
                Targets(
                    one=row["1"],
                    two=row["2"],
                    three=row["3"],
                    four=row["4"],
                    five=row["5"],
                    six=row["6"],
                    TONAME=row["TONAME"],
                    EMAIL=row["EMAIL"],
                )
                for index, row in target.iterrows()
            ]
            session.add_all(objects)
        else:
            objects = Targets(
                id=1,
                one="",
                two="",
                three="",
                four="",
                five="",
                six="",
                TONAME="",
                EMAIL="",
            )
            session.add(objects)
        session.commit()
        return (True, None)
    except Exception as e:
        logger.error(f"Error while loading Target: {e}")
        session.rollback()
        return (False, e)


def file_to_db():
    session = get_session()
    logger.info(f"File loading Config: {var.db_file_loading_config}")
    group_header = [
        "FIRSTFROMNAME",
        "LASTFROMNAME",
        "EMAIL",
        "EMAIL_PASS",
        "PROXY:PORT",
        "PROXY_USER",
        "PROXY_PASS",
    ]
    target_header = ["1", "2", "3", "4", "5", "6", "TONAME", "EMAIL"]
    try:
        if var.db_file_loading_config["group_a"]:
            clear_table(group_a=True)
            if os.path.exists(var.base_dir + "/group_a.xlsx"):
                group_a = pd.read_excel(
                    var.base_dir + "/group_a.xlsx",
                    engine="openpyxl",
                    sheet_name="group_a",
                )
                group_a = group_a[group_header]
                if list(group_a.keys()) == group_header:
                    group_a.fillna(" ", inplace=True)
                    group_a = group_a.astype(str)
                    group_a = group_a.loc[group_a["PROXY:PORT"] != " "]
                    if len(group_a) > 0:
                        objects = [
                            Group_A(
                                FIRSTFROMNAME=row["FIRSTFROMNAME"],
                                LASTFROMNAME=row["LASTFROMNAME"],
                                EMAIL=row["EMAIL"],
                                EMAIL_PASS=row["EMAIL_PASS"],
                                PROXY_PORT=row["PROXY:PORT"],
                                PROXY_USER=row["PROXY_USER"],
                                PROXY_PASS=row["PROXY_PASS"],
                            )
                            for index, row in group_a.iterrows()
                        ]
                        update_mail_server_config(objects)
                        session.add_all(objects)
                    else:
                        objects = Group_A(
                            id=1,
                            FIRSTFROMNAME="",
                            LASTFROMNAME="",
                            EMAIL="",
                            EMAIL_PASS="",
                            PROXY_PORT="",
                            PROXY_USER="",
                            PROXY_PASS="",
                        )
                        session.add(objects)
                    session.commit()
                else:
                    raise Exception("Header's not matching on Group A.")
            else:
                raise Exception("Group A file not found.")
        else:
            print("skipping Group A")
    except Exception as e:
        logger.error(f"Error while loading Group A: {e}")
        dummy_data_db(group_a=True, group_b=False, target=False)
        return (False, e)
    try:
        if var.db_file_loading_config["group_b"]:
            clear_table(group_b=True)
            if os.path.exists(var.base_dir + "/group_b.xlsx"):
                group_b = pd.read_excel(
                    var.base_dir + "/group_b.xlsx",
                    engine="openpyxl",
                    sheet_name="group_b",
                )
                group_b = group_b[group_header]
                if list(group_b.keys()) == group_header:
                    group_b.fillna(" ", inplace=True)
                    group_b = group_b.astype(str)
                    group_b = group_b.loc[group_b["PROXY:PORT"] != " "]
                    if len(group_b) > 0:
                        objects = [
                            Group_B(
                                FIRSTFROMNAME=row["FIRSTFROMNAME"],
                                LASTFROMNAME=row["LASTFROMNAME"],
                                EMAIL=row["EMAIL"],
                                EMAIL_PASS=row["EMAIL_PASS"],
                                PROXY_PORT=row["PROXY:PORT"],
                                PROXY_USER=row["PROXY_USER"],
                                PROXY_PASS=row["PROXY_PASS"],
                            )
                            for index, row in group_b.iterrows()
                        ]
                        update_mail_server_config(objects)
                        session.add_all(objects)
                    else:
                        objects = Group_B(
                            id=1,
                            FIRSTFROMNAME="",
                            LASTFROMNAME="",
                            EMAIL="",
                            EMAIL_PASS="",
                            PROXY_PORT="",
                            PROXY_USER="",
                            PROXY_PASS="",
                        )
                        session.add(objects)
                    session.commit()
                else:
                    raise Exception("Header's not matching on Group B.")
            else:
                raise Exception("Group B file not found.")
        else:
            print("skipping Group B")
    except Exception as e:
        logger.error(f"Error while loading Group B: {e}")
        dummy_data_db(group_a=False, group_b=True, target=False)
        return (False, e)
    try:
        if var.db_file_loading_config["target"]:
            clear_table(target=True)
            if os.path.exists(var.base_dir + "/target.xlsx"):
                target = pd.read_excel(
                    var.base_dir + "/target.xlsx",
                    engine="openpyxl",
                    sheet_name="target",
                )
                target.columns = target.columns.astype(str)
                target = target[target_header]
                if list(target.keys()) == target_header:
                    target.fillna(" ", inplace=True)
                    target = target.astype(str)
                    target = target.loc[target["EMAIL"] != " "]
                    if len(var.target_blacklist) > 0:
                        target = target[
                            ~target["EMAIL"]
                            .str.lower()
                            .str.contains("|".join(var.target_blacklist))
                        ]
                    if len(target) > 0:
                        objects = [
                            Targets(
                                one=row["1"],
                                two=row["2"],
                                three=row["3"],
                                four=row["4"],
                                five=row["5"],
                                six=row["6"],
                                TONAME=row["TONAME"],
                                EMAIL=row["EMAIL"],
                            )
                            for index, row in target.iterrows()
                        ]
                        session.add_all(objects)
                    else:
                        objects = Targets(
                            id=1,
                            one="",
                            two="",
                            three="",
                            four="",
                            five="",
                            six="",
                            TONAME="",
                            EMAIL="",
                        )
                        session.add(objects)
                    session.commit()
                else:
                    raise Exception("Header's not matching on Target.")
            else:
                raise Exception("Target file not found.")
        else:
            print("skipping Target")
    except Exception as e:
        logger.error(f"Error while loading Target: {e}")
        dummy_data_db(group_a=False, group_b=False, target=True)
        return (False, e)
    return (True, None)


def update_mail_server_config(objects):
    new_domain_config = {
        "imap": {"server": "imap.gmail.com", "port": 993},
        "smtp": {"server": "smtp.gmail.com", "port": 587, "require_ssl": False},
    }
    for obj in objects:
        if not obj.EMAIL or "@" not in obj.EMAIL:
            logger.error(f"Skipping invalid email: {obj.EMAIL}")
            continue
        regex = re.compile("(?<=@)(\\S+$)")
        mail_domain = regex.findall(obj.EMAIL)[0]
        parts = mail_domain.split(".")
        if len(parts) > 2:
            mail_vendor = ".".join(parts[:-1])
        elif len(parts) == 2:
            mail_vendor = parts[0]
        else:
            mail_vendor = mail_domain
        if mail_vendor not in var.mail_server:
            var.mail_server[mail_vendor] = new_domain_config
            var.data["config"]["mail_server"] = var.mail_server
            with open(
                f"{var.base_dir}/config.json", "w", encoding="utf-8"
            ) as json_file:
                json.dump(var.data, json_file, indent=4)


def dummy_data_db(group_a=True, group_b=True, target=True):
    session = get_session()
    if group_a:
        objects = Group_A(
            id=1,
            FIRSTFROMNAME="",
            LASTFROMNAME="",
            EMAIL="",
            EMAIL_PASS="",
            PROXY_PORT="",
            PROXY_USER="",
            PROXY_PASS="",
        )
        session.add(objects)
    if group_b:
        objects = Group_B(
            id=1,
            FIRSTFROMNAME="",
            LASTFROMNAME="",
            EMAIL="",
            EMAIL_PASS="",
            PROXY_PORT="",
            PROXY_USER="",
            PROXY_PASS="",
        )
        session.add(objects)
    if target:
        objects = Targets(
            id=1,
            one="",
            two="",
            three="",
            four="",
            five="",
            six="",
            TONAME="",
            EMAIL="",
        )
        session.add(objects)
    session.commit()


def pandas_to_db(group_a=None, group_b=None, target=None):
    try:
        session = get_session()
        if group_a:
            objects = [
                Group_A(
                    FIRSTFROMNAME=row["FIRSTFROMNAME"],
                    LASTFROMNAME=row["LASTFROMNAME"],
                    EMAIL=row["EMAIL"],
                    EMAIL_PASS=row["EMAIL_PASS"],
                    PROXY_PORT=row["PROXY:PORT"],
                    PROXY_USER=row["PROXY_USER"],
                    PROXY_PASS=row["PROXY_PASS"],
                )
                for index, row in var.group_a.iterrows()
            ]
            session.add_all(objects)
        if group_b:
            objects = [
                Group_B(
                    FIRSTFROMNAME=row["FIRSTFROMNAME"],
                    LASTFROMNAME=row["LASTFROMNAME"],
                    EMAIL=row["EMAIL"],
                    EMAIL_PASS=row["EMAIL_PASS"],
                    PROXY_PORT=row["PROXY:PORT"],
                    PROXY_USER=row["PROXY_USER"],
                    PROXY_PASS=row["PROXY_PASS"],
                )
                for index, row in var.group_b.iterrows()
            ]
            session.add_all(objects)
        if target:
            objects = [
                Targets(
                    one=row["1"],
                    two=row["2"],
                    three=row["3"],
                    four=row["4"],
                    five=row["5"],
                    six=row["6"],
                    TONAME=row["TONAME"],
                    EMAIL=row["EMAIL"],
                )
                for index, row in var.target.iterrows()
            ]
            session.add_all(objects)
        session.commit()
        logger.info("Pandas to DB done!")
    except Exception as e:
        logger.error(f"Error at var.pandas_to_db - {e}")


def db_to_pandas(group_a=None, group_b=None, target=None):
    session = get_session()
    if group_a:
        results = session.query(Group_A).all()
        group_a_list = [
            {
                "ID": item.id,
                "FIRSTFROMNAME": item.FIRSTFROMNAME,
                "LASTFROMNAME": item.LASTFROMNAME,
                "EMAIL": item.EMAIL,
                "EMAIL_PASS": item.EMAIL_PASS,
                "PROXY:PORT": item.PROXY_PORT,
                "PROXY_USER": item.PROXY_USER,
                "PROXY_PASS": item.PROXY_PASS,
            }.copy()
            for item in results
        ]
        var.group_a = pd.DataFrame(group_a_list)
    if group_b:
        results = session.query(Group_B).all()
        group_b_list = [
            {
                "ID": item.id,
                "FIRSTFROMNAME": item.FIRSTFROMNAME,
                "LASTFROMNAME": item.LASTFROMNAME,
                "EMAIL": item.EMAIL,
                "EMAIL_PASS": item.EMAIL_PASS,
                "PROXY:PORT": item.PROXY_PORT,
                "PROXY_USER": item.PROXY_USER,
                "PROXY_PASS": item.PROXY_PASS,
            }.copy()
            for item in results
        ]
        var.group_b = pd.DataFrame(group_b_list)

    def target_push(_session):
        _results = _session.query(Targets).all()
        targets_list = [
            {
                "ID": item.id,
                "1": item.one,
                "2": item.two,
                "3": item.three,
                "4": item.four,
                "5": item.five,
                "6": item.six,
                "TONAME": item.TONAME,
                "EMAIL": item.EMAIL,
            }.copy()
            for item in _results
        ]
        var.target = pd.DataFrame(targets_list)

    if target:
        results = session.query(Targets).all()
        if len(results) > 0:
            target_push(session)
        else:
            dummy_data_db(group_a=False, group_b=False, target=True)
            target_push(session)
    else:
        dummy_data_db(group_a=False, group_b=False, target=True)
        target_push(session)
    print(var.group_a.head(5))
    print(var.group_b.head(5))
    print(var.target.head(5))


def clear_table(group_a=None, group_b=None, target=None):
    try:
        session = get_session()
        if group_a:
            session.query(Group_A).delete()
        if group_b:
            session.query(Group_B).delete()
        if target:
            session.query(Targets).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error at clear DB table - {e}")


def load_db():
    try:
        result, error = file_to_db()
        db_to_pandas(group_a=True, group_b=True, target=True)
        var.command_q.put("self.update_db_table()")
        if result:
            alert(text="Database Loaded Successfully", title="Alert", button="OK")
        else:
            raise error
    except Exception as e:
        logger.error("Exception occured at DB loading : {}".format(e))
        alert(
            text="Exception occured at DB loading : {}".format(e),
            title="Alert",
            button="OK",
        )


def startup_load_db(parent=None):
    try:
        session = get_session()
        group_a = True if session.query(Group_A).first() == None else False
        group_b = True if session.query(Group_B).first() == None else False
        target = True if session.query(Targets).first() == None else False
        dummy_data_db(group_a=group_a, group_b=group_b, target=target)
        db_to_pandas(group_a=True, group_b=True, target=True)
        var.command_q.put("self.update_db_table()")
    except Exception as e:
        logger.error("Exeception occured at startup_db loading : {}".format(e))
        alert(
            text="Exeception occured at startup_db loading : {}".format(e),
            title="Alert",
            button="OK",
        )


class PullTargetAirtable(threading.Thread):
    still_running = False

    def __init__(self):
        super().__init__()
        self.setDaemon(True)
        self.config = var.AirtableConfig
        self.table = Table(
            self.config.api_key, self.config.base_id, self.config.table_name
        )

    def run(self) -> None:
        PullTargetAirtable.still_running = True
        try:
            logger.info("Starting pulling data from airtable")
            if self.config.use_desktop_id:
                targets = self.get_data_with_desktop_id()
            else:
                targets = self.get_data()
            targets = self.rearrange_data(targets)
            target_df = pd.DataFrame(targets)
            if len(target_df) > 0:
                var.target = target_df
                # clear targets from db
                clear_table(group_a=None, group_b=None, target=True)

                # pandas to db
                pandas_to_db(group_a=None, group_b=None, target=True)
                db_to_pandas(group_a=None, group_b=None, target=True)
                var.command_q.put("self.update_db_table()")
                logger.info("Completed pulling data from airtable")
                # alert("Pulling Data Done", title="Success", button="OK")

            else:
                logger.info("Completed pulling data from airtable But It was empty.")
                # alert(text="Empty Table", title="Failed", button="OK")

        except Exception as e:
            logger.error(
                f"Error in {self.__class__.__name__}: {traceback.format_exc()}"
            )
            alert(f"{e}", title=f"Error at {self.__class__.__name__}", button="OK")
        finally:
            PullTargetAirtable.still_running = False

    def get_data(self):
        logger.info(
            f"{self.__class__.__name__} - Downloading data from airtable without desktop id"
        )
        formula = match({"has_sent_email": 0})
        results = self.table.all(formula=formula)
        logger.info(
            f"{self.__class__.__name__} - Downloading data from airtable without desktop id: DONE"
        )
        return results

    def get_data_with_desktop_id(self):
        logger.info(
            f"{self.__class__.__name__} - Downloading data from airtable without desktop id"
        )
        formula = match(
            {"desktop_app_id": var.gmonster_desktop_id, "has_sent_email": 0}
        )
        results = self.table.all(formula=formula)
        logger.info(
            f"{self.__class__.__name__} - Downloading data from airtable without desktop id: DONE"
        )
        return results

    def rearrange_data(self, targets):
        logger.info(f"{self.__class__.__name__} - Rearranging data")
        list_of_targets = []
        for item in targets:
            temp = item["fields"]
            row = dict()
            if "EMAIL" in temp and temp["EMAIL"].strip() != "":
                row["1"] = temp["1"] if "1" in temp else ""
                row["2"] = temp["2"] if "2" in temp else ""
                row["3"] = temp["3"] if "3" in temp else ""
                row["4"] = temp["4"] if "4" in temp else ""
                row["5"] = temp["5"] if "5" in temp else ""
                row["6"] = temp["6"] if "6" in temp else ""
                row["TONAME"] = temp["TONAME"] if "TONAME" in temp else ""
                row["EMAIL"] = temp["EMAIL"] if "EMAIL" in temp else ""
                list_of_targets.append(row.copy())
            else:
                logger.error(
                    "EMPTY or MISSING email while downloading TARGET data from airtable"
                )
        return list_of_targets
