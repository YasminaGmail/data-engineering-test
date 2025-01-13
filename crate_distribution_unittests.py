import pandas as pd
import json
from collections import defaultdict
import unittest
import re

def clean_contact_data(contact_data):
    """
    Attempt to clean and fix malformed JSON data.
    """
    try:
        # Replace NaN or empty values with an empty list
        if pd.isna(contact_data) or not contact_data.strip():
            return "[]"

        # Fix missing brackets or trailing commas
        cleaned_data = contact_data.strip()
        if not cleaned_data.startswith('['):
            cleaned_data = '[' + cleaned_data
        if not cleaned_data.endswith(']'):
            cleaned_data += ']'
        
        # Validate JSON
        json.loads(cleaned_data)  # Will raise an error if still invalid
        return cleaned_data
    except (json.JSONDecodeError, TypeError):
        # Log and replace with a default empty list
        print(f"Malformed contact_data: {contact_data}")
        return "[]"


# Load the orders.csv file
def load_orders(orders_file):
    """
    Load the orders CSV file into a Pandas DataFrame.
    """
    # Load the CSV file with the correct delimiter
    orders_df = pd.read_csv(orders_file, delimiter=';') 
    # Standardize column names
    orders_df.columns = orders_df.columns.str.strip().str.lower()  
    return orders_df

# Load the invoicing_data.json file
def load_invoicing_data(invoicing_file):
    """
    Load the invoicing data JSON file into a list.
    """
    with open(invoicing_file, 'r') as f:
        return json.load(f)




# TEST1: Calculate the distribution of crate types per company
def crate_type_distribution(orders_df):
    """
    Calculate the distribution of crate types per company.
    """
    if 'company_name' not in orders_df.columns or 'crate_type' not in orders_df.columns:
        raise ValueError("Missing required columns: 'company_name' or 'crate_type'")
    distribution = orders_df.groupby(['company_name', 'crate_type']).size().unstack(fill_value=0)
    return distribution

# TEST2: Full name of the contact
def generate_contact_full_name(orders_df):
    """
    Extract contact_name and contact_surname from the JSON-like contact_data column,
    and generate contact_full_name as their concatenation.
    """
    if 'contact_data' not in orders_df.columns:
        raise ValueError("The 'contact_data' column is missing in the orders data.")
    
    def extract_full_name(contact_data):
        """
        Extract contact_name and contact_surname from the JSON string
        and return the concatenated full name.
        """
        try:
            # Clean and validate contact_data
            contact_data = clean_contact_data(contact_data)
            
            # Parse JSON data
            contacts = json.loads(contact_data)
            if isinstance(contacts, list) and len(contacts) > 0:
                contact_name = contacts[0].get("contact_name", "John")
                contact_surname = contacts[0].get("contact_surname", "Doe")
                return f"{contact_name} {contact_surname}"
            else:
                return "John Doe"
        except (json.JSONDecodeError, IndexError, TypeError) as e:
            print(f"Error parsing contact_data: {contact_data} -> {e}")
            return "John Doe"
    
    # Apply the extraction function to the contact_data column
    orders_df['contact_full_name'] = orders_df['contact_data'].apply(extract_full_name)
    return orders_df[['order_id', 'contact_full_name']]



# TEST3: Orders with contact address
def generate_contact_address(orders_df):
    """
    Extract city and postal_code from the JSON-like contact_data column,
    and generate contact_address as 'city, postal_code'.
    """
    if 'contact_data' not in orders_df.columns:
        raise ValueError("The 'contact_data' column is missing in the orders data.")
    
    def extract_address(contact_data):
        """
        Extract city and postal_code from the JSON string
        and return the formatted address.
        """
        try:
            # Clean and validate contact_data
            contact_data = clean_contact_data(contact_data)
            
            # Parse JSON data
            contacts = json.loads(contact_data)
            if isinstance(contacts, list) and len(contacts) > 0:
                city = contacts[0].get("city", "Unknown")
                postal_code = contacts[0].get("cp", "UNK00")
                return f"{city}, {postal_code}"
            else:
                return "Unknown, UNK00"
        except (json.JSONDecodeError, IndexError, TypeError) as e:
            print(f"Error parsing contact_data: {contact_data} -> {e}")
            return "Unknown, UNK00"
    
    # Apply the extraction function to the contact_data column
    orders_df['contact_address'] = orders_df['contact_data'].apply(extract_address)
    return orders_df[['order_id', 'contact_address']]




# TEST4: Sales Teams commissions
def calculate_commissions(orders_df, invoicing_data):
    """
    Calculate commissions for sales owners based on the invoicing data.
    Handles nested JSON structure for invoicing_data.
    """
    try:
        # Extract 'invoices' list from the nested JSON
        invoices = invoicing_data.get("data", {}).get("invoices", [])
        if not invoices:
            raise ValueError("No 'invoices' data found in invoicing_data.")

        # Convert to DataFrame and rename columns
        invoicing_df = pd.DataFrame(invoices)
        invoicing_df.rename(columns={
            'orderId': 'order_id',
            'grossValue': 'gross_value',
            'vat': 'vat'
        }, inplace=True)

        # Ensure data types are consistent
        invoicing_df['gross_value'] = pd.to_numeric(invoicing_df['gross_value'], errors='coerce')
        invoicing_df['vat'] = pd.to_numeric(invoicing_df['vat'], errors='coerce')

        # Clean order_id columns
        orders_df['order_id'] = orders_df['order_id'].str.strip()
        invoicing_df['order_id'] = invoicing_df['order_id'].str.strip()

        # Merge orders with invoicing data
        merged_df = orders_df.merge(invoicing_df, on="order_id", how="inner")

        # Collect commission data
        commission_data = []
        for _, row in merged_df.iterrows():
            salesowners = row['salesowners'].split(',')
            net_value = row['gross_value'] / 100  # Convert cents to euros

            # Main owner
            if len(salesowners) > 0:
                commission_data.append((salesowners[0].strip(), net_value * 0.06))
            # Co-owner 1
            if len(salesowners) > 1:
                commission_data.append((salesowners[1].strip(), net_value * 0.025))
            # Co-owner 2
            if len(salesowners) > 2:
                commission_data.append((salesowners[2].strip(), net_value * 0.0095))

        # Aggregate commissions by salesowner
        commission_df = pd.DataFrame(commission_data, columns=['salesowner', 'commission'])
        commission_df = (
            commission_df.groupby('salesowner', as_index=False)['commission']
            .sum()
            .sort_values(by=['commission', 'salesowner'], ascending=[False, True])
        )

        return commission_df

    except KeyError as e:
        raise ValueError(f"Missing key in invoicing_data: {e}")
    except Exception as e:
        raise RuntimeError(f"Error while calculating commissions: {e}")




# TEST5: Companies with Sales Owners
def generate_company_salesowners(orders_df):
    """
    Generate a DataFrame of companies with a sorted, unique list of salesowners.
    """
    orders_df['salesowners'] = orders_df['salesowners'].str.split(',')
    company_sales = (
        orders_df.explode('salesowners')
        .groupby(['company_id', 'company_name'])['salesowners']
        .apply(lambda x: ','.join(sorted(set(x))))  # Sort unique salesowners
    )
    return company_sales.reset_index()


# Unit tests
class TestCrateDistribution(unittest.TestCase):
    def setUp(self):
        """Mock orders data for testing."""
        self.orders_data = {
            "order_id": [1, 2, 3, 4, 5],
            "date": ["2024-12-01", "2024-12-02", "2024-12-03", "2024-12-04", "2024-12-05"],
            "company_id": [101, 102, 101, 103, 102],
            "company_name": ["Company A", "Company B", "Company A", "Company C", "Company B"],
            "crate_type": ["Type 1", "Type 2", "Type 1", "Type 3", "Type 2"],
            "contact_full_name": ["Alice Smith", None, "Bob Brown", None, "John Doe"],
            "city": ["New York", "Chicago", None, "Los Angeles", "Chicago"],
            "postal_code": ["10001", "20002", "30001", None, None],
            "salesowners": ["owner1", "owner2", "owner1", "owner3", "owner2"]
        }
        self.orders_df = pd.DataFrame(self.orders_data)
        self.invoicing_data = [
            {"order_id": 1, "net_invoiced_value": 10000},
            {"order_id": 2, "net_invoiced_value": 20000},
            {"order_id": 3, "net_invoiced_value": 30000},
            {"order_id": 4, "net_invoiced_value": 40000},
            {"order_id": 5, "net_invoiced_value": 50000},
        ]

    def test_crate_type_distribution(self):
        """Test the crate type distribution calculation."""
        expected_output = pd.DataFrame({
            "Type 1": [2, 0, 0],
            "Type 2": [0, 2, 0],
            "Type 3": [0, 0, 1]
        }, index=["Company A", "Company B", "Company C"])
        expected_output.index.name = "company_name"
        expected_output.columns.name = "crate_type"
        result = crate_type_distribution(self.orders_df)
        pd.testing.assert_frame_equal(result, expected_output)

    def test_generate_contact_full_name(self):
        """Test generation of contact full name with missing values."""
        result = generate_contact_full_name(self.orders_df)
        expected_output = pd.DataFrame({
            "order_id": [1, 2, 3, 4, 5],
            "contact_full_name": ["Alice Smith", "John Doe", "Bob Brown", "John Doe", "John Doe"]
        })
        pd.testing.assert_frame_equal(result, expected_output)

    def test_generate_contact_address(self):
        """Test generation of contact address with placeholders."""
        result = generate_contact_address(self.orders_df)
        expected_output = pd.DataFrame({
            "order_id": [1, 2, 3, 4, 5],
            "contact_address": [
                "New York, 10001",
                "Chicago, 20002",
                "Unknown, 30001",
                "Los Angeles, UNK00",
                "Chicago, UNK00"
            ]
        })
        pd.testing.assert_frame_equal(result, expected_output)

    def test_calculate_commissions(self):
        """Test calculation of sales team commissions."""
        result = calculate_commissions(self.orders_df, self.invoicing_data)

        # Correct expected output sorted by commission descending and salesowner alphabetically
        expected_output = pd.DataFrame({
            "salesowner": ["owner2", "owner1", "owner3"],
            "commission": [42.0, 24.0, 24.0]
        })

        # Compare the DataFrames after resetting the index
        result = result.reset_index(drop=True)
        expected_output = expected_output.reset_index(drop=True)

        pd.testing.assert_frame_equal(result, expected_output)

    def test_generate_company_salesowners(self):
        """Test generation of unique, sorted salesowners list by company."""
        result = generate_company_salesowners(self.orders_df)
        expected_output = pd.DataFrame({
            "company_id": [101, 102, 103],
            "company_name": ["Company A", "Company B", "Company C"],
            "salesowners": ["owner1", "owner2", "owner3"]  # Alphabetically sorted
        })
        pd.testing.assert_frame_equal(result.sort_index(), expected_output.sort_index())






if __name__ == "__main__":
    # Specify file paths
    orders_file = r"C:\Users\yhernandez\OneDrive\Desktop\PythonProjects\orders.csv"
    invoicing_file = r"C:\Users\yhernandez\OneDrive\Desktop\PythonProjects\invoicing_data.json"

    try:
        # Load data
        orders_df = load_orders(orders_file)
        invoicing_data = load_invoicing_data(invoicing_file)

        # Generate and print all required dataframes
        print("\n--- Test 1: Crate Type Distribution (df) ---")
        df = crate_type_distribution(orders_df)
        print(df)

        print("\n--- Test 2: Orders with Contact Full Name (df_1) ---")
        df_1 = generate_contact_full_name(orders_df)
        print(df_1)

        print("\n--- Test 3: Orders with Contact Address (df_2) ---")
        df_2 = generate_contact_address(orders_df)
        print(df_2)

        print("\n--- Test 4: Sales Team Commissions ---")
        df_commissions = calculate_commissions(orders_df, invoicing_data)
        print(df_commissions)

        print("\n--- Test 5: Companies with Sales Owners (df_3) ---")
        df_3 = generate_company_salesowners(orders_df)
        print(df_3)

        # Run unit tests
        #print("\n--- Running Unit Tests ---")
        #unittest.main(exit=False)

    except FileNotFoundError as e:
        print(f"File not found: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
