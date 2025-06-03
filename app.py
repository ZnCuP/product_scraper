import streamlit as st
import pandas as pd
import json
import os
import glob

DATA_DIR = "data"

@st.cache_data # Streamlit 缓存装饰器，避免重复加载数据
def load_latest_products_data(data_dir):
    """
    加载 data 文件夹中最新的 all_products_*.json 文件。
    """
    try:
        list_of_files = glob.glob(os.path.join(data_dir, 'all_products_*.json'))
        if not list_of_files:
            return None
        latest_file = max(list_of_files, key=os.path.getctime)
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"加载数据文件失败: {e}")
        return None

def main():
    st.set_page_config(layout="wide", page_title="A-Premium 产品查看器") # 确保这行只在 main() 的开头调用一次
    st.title("A-Premium 产品数据查看器")

    df_products_original = load_latest_products_data(DATA_DIR)

    if df_products_original is None or df_products_original.empty:
        st.warning("未能加载产品数据或数据为空。请确保 'data' 文件夹中有 'all_products_*.json' 文件。")
        return

    df_display = df_products_original.copy() # 用于筛选和搜索的DataFrame副本

    st.sidebar.header("筛选和搜索")

    # 1. 按分类筛选
    if 'category' in df_display.columns:
        unique_categories = ["所有分类"] + sorted(df_display['category'].astype(str).unique().tolist())
        selected_category = st.sidebar.selectbox("按产品主分类筛选 (Filter by Category)", unique_categories)
        if selected_category != "所有分类":
            df_display = df_display[df_display['category'] == selected_category]
    else:
        st.sidebar.text("数据中未找到 'category' 字段用于分类。")

    # 2. 关键词搜索
    search_term = st.sidebar.text_input("搜索 (Search by Name, SKU, Item No., Brand, OE, etc.)")

    # df_search_target 用于搜索，df_display 用于后续的筛选结果
    df_search_target = df_display.copy()

    if search_term:
        search_cols = ['name', 'sku', 'item_number', 'brand', 'category', 'oe_number', 'interchange_number', 'fitment']
        cols_to_search = [col for col in search_cols if col in df_search_target.columns]
        
        # 在 df_temp_search 中进行必要的类型转换以供搜索
        df_temp_search_for_string_search = df_search_target.copy()
        for col in cols_to_search:
            # 确保在搜索前，所有列都转换为字符串，特别是列表类型
            # 检查 Series 中的任何元素是否为列表
            is_list_series = df_temp_search_for_string_search[col].apply(type).eq(list).any()
            if is_list_series:
                df_temp_search_for_string_search[col] = df_temp_search_for_string_search[col].apply(
                    lambda x: '; '.join(map(str, x)) if isinstance(x, list) else str(x)
                )
            # 如果 SKU 或 Fitment 在原始数据中是特定分隔的字符串，也在这里处理以便搜索
            elif col == 'sku' and isinstance(df_temp_search_for_string_search[col].iloc[0], str): # 假设SKU是字符串
                 pass # SKU 通常已经是单个字符串或逗号分隔的字符串，搜索时可以直接用
            elif col == 'fitment' and isinstance(df_temp_search_for_string_search[col].iloc[0], str): # Fitment是分号分隔的字符串
                 pass # Fitment 已经是字符串，搜索时可以直接用
            else:
                df_temp_search_for_string_search[col] = df_temp_search_for_string_search[col].astype(str)
        
        mask = df_temp_search_for_string_search[cols_to_search].apply(
            lambda row: row.str.contains(search_term, case=False, na=False)
        ).any(axis=1)
        df_display = df_search_target[mask] # 从包含原始数据类型的 df_search_target 中应用掩码

    st.header("产品列表 (Product List)")
    st.write(f"共找到 {len(df_display)} 条产品记录 (Found {len(df_display)} records)")

    column_mapping = {
        'name': 'Name (产品名称)',
        'sku': 'SKU',
        'item_number': 'Item Number (物料号)',
        'price': 'Price (价格)',
        'original_price': 'Original Price (原价)',
        'category': 'Category (分类)',
        'brand': 'Brand (品牌)',
        'availability': 'Availability (库存状态)',
        'sales': 'Sales (销量)',
        'review_count': 'Review Count (评论数)',
        'review_rating': 'Review Rating (评分)',
        'warranty': 'Warranty (质保)',
        'fitment': 'Fitment (适配车型)',
        'oe_number': 'OE Number (OE号)',
        'interchange_number': 'Interchange Number (替换号)',
        'url': 'Product URL (产品链接)',
        'image_url': 'Image URL (图片链接)',
        # 'specifications': 'Specifications (规格)', # 已移除
        'material': 'Material (材质)',
        'color': 'Color (颜色)',
        'installation': 'Installation (安装方式)'
    }

    original_display_columns_order = [
        'name', 'sku', 'item_number', 'price', 'category', 'brand',
        'availability', 'sales', 'fitment', 'oe_number', 
        'material', 'color', 'installation', # 'specifications' 已从这里移除
        'url', 'image_url'
    ]
    
    actual_original_columns = [col for col in original_display_columns_order if col in df_display.columns]
    
    df_for_table_display = df_display[actual_original_columns].copy()
    
    # 处理 SKU 以便显示为标签
    if 'sku' in df_for_table_display.columns:
        # 确保 sku 列是字符串类型，以便安全地使用 .str accessor
        # 对于已经是列表的（虽然根据爬虫不太可能），或者数字等，先转为字符串
        # 如果原始数据中 sku 可能为 None，fillna('') 避免了 None.split() 错误
        df_for_table_display['sku'] = df_for_table_display['sku'].fillna('').astype(str).apply(
            lambda x: [s.strip() for s in x.split(',') if s.strip()] if x else []
        )

    # 处理 Fitment 以便显示为标签
    if 'fitment' in df_for_table_display.columns:
        df_for_table_display['fitment'] = df_for_table_display['fitment'].fillna('').astype(str).apply(
            lambda x: [s.strip() for s in x.split(';')] if x.strip() else []
        )
    
    # oe_number 和 interchange_number 已经是列表，无需再处理以显示为标签

    # 格式化 specifications 列 (字典类型) 为可读字符串
    # if 'specifications' in df_for_table_display.columns:
    #     df_for_table_display['specifications'] = df_for_table_display['specifications'].apply(
    #         lambda specs_dict: "\n".join([f"{k}: {v}" for k, v in specs_dict.items()]) if isinstance(specs_dict, dict) and specs_dict else ""
    #     )

    df_for_table_display.rename(columns=column_mapping, inplace=True)
    
    # 定义列配置，特别是链接列
    column_config_dict = {}
    if 'Product URL (产品链接)' in df_for_table_display.columns:
        column_config_dict['Product URL (产品链接)'] = st.column_config.LinkColumn(
            "产品链接", # 列的显示名称
            help="点击打开产品页面",
            display_text="打开链接" # 链接显示的文本
        )
    if 'Image URL (图片链接)' in df_for_table_display.columns:
        column_config_dict['Image URL (图片链接)'] = st.column_config.LinkColumn(
            "图片链接", 
            help="点击查看图片",
            display_text="查看图片"
        )
    # 你可以为其他列也添加配置，例如数字格式化等
    # column_config_dict['Price (价格)'] = st.column_config.NumberColumn(format="$ %.2f")


    if not df_for_table_display.empty:
        st.dataframe(
            df_for_table_display,
            column_config=column_config_dict if column_config_dict else None,
            hide_index=True # 通常隐藏索引更美观
        )
    else:
        st.info("没有找到符合条件的产品。 (No products found matching your criteria.)")

if __name__ == "__main__":
    main()
