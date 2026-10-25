FIRST_M = ["Ramesh", "Suresh", "Venkata", "Srinivas", "Ravi", "Kiran", "Praveen", "Rajesh", "Anil", "Sanjay", "Mahesh",
           "Naveen", "Arun", "Vijay", "Prakash", "Sunil", "Ashok", "Ganesh", "Harish", "Manoj", "Deepak", "Rahul",
           "Amit", "Nitin", "Sachin", "Vinod", "Rakesh", "Karthik", "Siva", "Murali", "Balaji", "Senthil", "Mohan",
           "Raghav", "Vivek", "Ajay", "Pavan", "Srikanth", "Chandra", "Narasimha", "Prasad", "Satish", "Sudhakar",
           "Yashwant", "Omkar", "Tushar", "Abhijit", "Shrikant", "Kumaravel", "Elango", "Dinesh", "Gopal"]
FIRST_F = ["Lakshmi", "Priya", "Swathi", "Anitha", "Kavitha", "Sravani", "Divya", "Madhavi", "Padma", "Sunitha", "Radha",
           "Deepa", "Neha", "Pooja", "Sneha", "Shweta", "Aarti", "Manisha", "Revathi", "Meena", "Bhavani", "Sowmya",
           "Haritha", "Keerthi", "Jyothi", "Vani", "Uma", "Gayathri", "Nandini", "Archana", "Rupali", "Smita",
           "Vaishali", "Malathi", "Saranya", "Indhu", "Anusha", "Mounika", "Ramya", "Sushma"]
SURNAMES = {
    "Telangana": ["Reddy", "Rao", "Goud", "Naidu", "Sharma", "Chary", "Varma", "Yadav", "Kumar", "Prasad", "Murthy",
                  "Babu", "Raju", "Shetty", "Sastry", "Kondapalli", "Gundlapalli", "Bandaru", "Pulipati", "Medapati"],
    "Maharashtra": ["Patil", "Deshmukh", "Kulkarni", "Joshi", "Pawar", "Shinde", "Jadhav", "More", "Gaikwad", "Chavan",
                    "Bhosale", "Deshpande", "Kale", "Thakur", "Wagh", "Salunkhe", "Mane", "Kadam", "Nikam", "Sawant"],
    "Tamil Nadu": ["Subramanian", "Krishnan", "Raman", "Natarajan", "Sundaram", "Pandian", "Murugan", "Selvam",
                   "Ramasamy", "Chandrasekaran", "Rajendran", "Govindan", "Kannan", "Arumugam", "Palanisamy",
                   "Venkatesan", "Duraisamy", "Shanmugam", "Velusamy", "Balasubramanian"],
}
QUALS = {"Professor": ["Ph.D", "Ph.D"], "Associate Professor": ["Ph.D", "Ph.D", "M.Tech"],
         "Assistant Professor": ["M.Tech", "M.Tech", "M.E", "Ph.D", "MBA", "MCA"]}

# Campus clusters: plausible peri-urban engineering-college belts (coordinates are area centroids).
CLUSTERS = {
    "Telangana": {
        "region": "South-Central", "city": "Hyderabad", "university": "Jawaharlal Nehru Technological University, Hyderabad",
        "fire": "Telangana State Fire & Emergency Services (Synthetic Registry)",
        "municipal": "Hyderabad Metropolitan Development Authority (Synthetic)",
        "state_code": "TS", "estamp_state": "TS",
        "localities": [("Ghatkesar", 17.4500, 78.6850, "Medchal-Malkajgiri"), ("Ibrahimpatnam", 17.1920, 78.6500, "Rangareddy"),
                       ("Shamshabad", 17.2530, 78.4000, "Rangareddy"), ("Medchal", 17.6290, 78.4810, "Medchal-Malkajgiri"),
                       ("Narsapur Road", 17.5600, 78.3300, "Medak"), ("Moinabad", 17.3260, 78.2700, "Rangareddy")],
    },
    "Maharashtra": {
        "region": "Western", "city": "Pune", "university": "Savitribai Phule Pune University",
        "fire": "Maharashtra Fire Services (Synthetic Registry)",
        "municipal": "Pune Metropolitan Region Development Authority (Synthetic)",
        "state_code": "MH", "estamp_state": "MH",
        "localities": [("Wagholi", 18.5800, 73.9800, "Pune"), ("Hinjewadi", 18.5910, 73.7380, "Pune"),
                       ("Talegaon", 18.7350, 73.6750, "Pune"), ("Lonikand", 18.6190, 74.0190, "Pune")],
    },
    "Tamil Nadu": {
        "region": "Southern", "city": "Coimbatore", "university": "Anna University, Chennai",
        "fire": "Tamil Nadu Fire and Rescue Services (Synthetic Registry)",
        "municipal": "Directorate of Town and Country Planning (Synthetic)",
        "state_code": "TN", "estamp_state": "TN",
        "localities": [("Malumichampatti", 10.9010, 76.9930, "Coimbatore"), ("Chettipalayam", 10.9150, 77.0270, "Coimbatore"),
                       ("Kinathukadavu", 10.8220, 77.0170, "Coimbatore"), ("Perur", 10.9750, 76.9130, "Coimbatore")],
    },
}
# Deliberately invented names (unusual compounds) so a synthetic forgery is never attached to a real college.
FOUNDERS = ["Tarangvani", "Swarnadeepa", "Nirmalgiri Vale", "Hemvati Kshetra", "Suryakiran Valley", "Ambarpeth",
            "Kalpataru Ridge", "Navadeepika", "Shaktikund", "Tejasvarna", "Vasundhara Hills", "Meghmalhar",
            "Indravati Crest", "Kesarveni", "Ilavarasi Nagar", "Chandrashila", "Neelkamal Tarai", "Pushpagiri Dhaam",
            "Sahasradhara Point", "Mrigavani", "Ratnaparvat", "Godavari Bloom", "Kaveri Ridge", "Amrutvel",
            "Vindhyashree", "Prabhatpura", "Sindhurekha", "Anandvan Heights", "Devgiri Meadows", "Jalataranga",
            "Kanakadhara Vale", "Tamravarni", "Sunehri Bagh", "Akashneel", "Harithavanam", "Shwetagiri"]
INST_SUFFIX = ["Institute of Engineering & Technology", "College of Engineering", "Institute of Technology",
               "College of Engineering and Management"]

# Engineering & Technology UG courses with realistic intake mixes (from the public EoA corpus).
UG_COURSES = [("COMPUTER SCIENCE AND ENGINEERING", [120, 180, 240, 300]),
              ("COMPUTER SCIENCE AND ENGINEERING (ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING)", [60, 120, 180]),
              ("COMPUTER SCIENCE AND ENGINEERING (DATA SCIENCE)", [60, 120]),
              ("ELECTRONICS AND COMMUNICATION ENGINEERING", [60, 120, 180]),
              ("ELECTRICAL AND ELECTRONICS ENGINEERING", [60]),
              ("MECHANICAL ENGINEERING", [60, 120]),
              ("CIVIL ENGINEERING", [60]),
              ("INFORMATION TECHNOLOGY", [60, 120]),
              ("ARTIFICIAL INTELLIGENCE AND DATA SCIENCE", [60, 120])]
PG_COURSES = [("MASTERS IN BUSINESS ADMINISTRATION", "MANAGEMENT", [60, 120], 2),
              ("MASTER OF COMPUTER APPLICATIONS", "COMPUTER APPLICATIONS", [60], 2)]
